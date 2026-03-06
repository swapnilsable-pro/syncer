"""Snap ASR word timestamps to canonical lyrics text using Levenshtein-based DP alignment."""

from dataclasses import dataclass
from typing import Optional

import Levenshtein

from syncer.models import SyncedLine, SyncedWord


@dataclass
class AlignedWord:
    """ASR output word with timestamp and confidence score."""

    word: str
    start: float
    end: float
    score: float = 0.0


# DP alignment constants
_MATCH_SCORE = 2
_FUZZY_SCORE = 1
_MISMATCH_PENALTY = -1
_GAP_PENALTY = -1
_FUZZY_THRESHOLD = 0.7


@dataclass
class _LyricsWord:
    """Internal: a word from lyrics with its position metadata."""

    word: str
    line_idx: int
    word_idx: int


def _flatten_lyrics(lyrics_lines: list[str]) -> list[_LyricsWord]:
    """Flatten lyrics lines into a flat word sequence with position metadata."""
    words: list[_LyricsWord] = []
    for line_idx, line in enumerate(lyrics_lines):
        for word_idx, word in enumerate(line.split()):
            if word.strip():
                words.append(
                    _LyricsWord(word=word.strip(), line_idx=line_idx, word_idx=word_idx)
                )
    return words


def _score_pair(asr_word: str, lyrics_word: str) -> int:
    """Score a word pair: +2 exact, +1 fuzzy (ratio > 0.7), -1 mismatch."""
    a = asr_word.lower().strip()
    b = lyrics_word.lower().strip()
    if a == b:
        return _MATCH_SCORE
    if Levenshtein.ratio(a, b) > _FUZZY_THRESHOLD:
        return _FUZZY_SCORE
    return _MISMATCH_PENALTY


def _align_dp(
    asr_words: list[AlignedWord], lyrics_words: list[_LyricsWord]
) -> list[tuple[int, Optional[int]]]:
    """
    Smith-Waterman-style DP alignment between ASR words and lyrics words.

    Returns list of (lyrics_word_idx, asr_word_idx_or_None) for every lyrics word.
    """
    n = len(asr_words)
    m = len(lyrics_words)

    # dp[i][j] = best score aligning asr[:i] with lyrics[:j]
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    # traceback: 0=none, 1=match/mismatch(diag), 2=skip-lyrics(left), 3=skip-asr(up)
    trace = [[0] * (m + 1) for _ in range(n + 1)]

    best_score = 0
    best_i, best_j = 0, 0

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            # Diagonal: match/mismatch
            pair_score = _score_pair(asr_words[i - 1].word, lyrics_words[j - 1].word)
            diag = dp[i - 1][j - 1] + pair_score
            # Up: skip ASR word (gap in lyrics)
            up = dp[i - 1][j] + _GAP_PENALTY
            # Left: skip lyrics word (gap in ASR)
            left = dp[i][j - 1] + _GAP_PENALTY

            # Smith-Waterman: allow restart from 0
            val = max(0, diag, up, left)
            dp[i][j] = val

            if val == 0:
                trace[i][j] = 0
            elif val == diag:
                trace[i][j] = 1
            elif val == up:
                trace[i][j] = 3
            else:
                trace[i][j] = 2

            if val >= best_score:
                best_score = val
                best_i, best_j = i, j

    # Traceback from best position
    matched: dict[int, int] = {}  # lyrics_word_idx -> asr_word_idx
    i, j = best_i, best_j
    while i > 0 and j > 0 and dp[i][j] > 0:
        t = trace[i][j]
        if t == 1:  # diagonal
            pair_score = _score_pair(asr_words[i - 1].word, lyrics_words[j - 1].word)
            if pair_score > 0:  # only record actual matches
                matched[j - 1] = i - 1
            i -= 1
            j -= 1
        elif t == 3:  # up (skip ASR)
            i -= 1
        elif t == 2:  # left (skip lyrics)
            j -= 1
        else:
            break

    # Build result: every lyrics word gets an optional ASR index
    result: list[tuple[int, Optional[int]]] = []
    for lw_idx in range(m):
        asr_idx = matched.get(lw_idx)
        result.append((lw_idx, asr_idx))

    return result


def _interpolate_timestamp(
    word_pos: int,
    total_words: int,
    left_match: Optional[tuple[float, float]],
    right_match: Optional[tuple[float, float]],
) -> tuple[float, float]:
    """Linearly interpolate timestamp for an unmatched word between neighbors."""
    if left_match is None and right_match is None:
        return 0.0, 0.0

    if left_match is None:
        # Before first match: spread from 0 to right_match start
        right_start, _ = right_match
        if word_pos == 0 or right_start <= 0:
            return 0.0, 0.0
        frac = word_pos / (word_pos + 1)
        t = right_start * frac
        dur = right_start / (word_pos + 1)
        return max(0.0, t - dur), t

    if right_match is None:
        # After last match: extend from left_match end
        _, left_end = left_match
        offset = 0.5 * ((word_pos + 1) / max(total_words, 1))
        start = left_end + offset - 0.3
        return max(left_end, start), left_end + offset

    # Between two matches: linear interpolation
    _, left_end = left_match
    right_start, _ = right_match
    span = right_start - left_end
    # word_pos is relative position; we need gap info
    # Use a simple even distribution
    return left_end, left_end + span * 0.5  # placeholder, refined below


def snap_words_to_lyrics(
    asr_words: list,  # list of AlignedWord (word, start, end, score)
    lyrics_lines: list[str],
) -> list[SyncedLine]:
    """
    Align ASR word timestamps to canonical lyrics text.

    Algorithm:
    1. Flatten lyrics into word sequence with (word, line_idx, word_idx_in_line)
    2. Run Smith-Waterman DP alignment between ASR words and lyrics words
    3. Walk back alignment to get matched pairs
    4. Assign timestamps: matched -> ASR timestamp, unmatched -> interpolated
    5. Group back into SyncedLine objects
    """
    if not lyrics_lines:
        return []

    lyrics_words = _flatten_lyrics(lyrics_lines)

    if not lyrics_words:
        return []

    # Handle empty ASR: return all lines with zero timestamps
    if not asr_words:
        lines: list[SyncedLine] = []
        for line_idx, line_text in enumerate(lyrics_lines):
            words_in_line = [w for w in lyrics_words if w.line_idx == line_idx]
            synced_words = [
                SyncedWord(text=w.word, start=0.0, end=0.0, confidence=0.0)
                for w in words_in_line
            ]
            if synced_words:
                lines.append(
                    SyncedLine(
                        text=line_text.strip(),
                        start=0.0,
                        end=0.0,
                        words=synced_words,
                    )
                )
        return lines

    # Run DP alignment
    alignment = _align_dp(asr_words, lyrics_words)

    # Build timestamp assignments for each lyrics word
    # First pass: assign matched timestamps
    timestamps: list[tuple[float, float, float]] = [(0.0, 0.0, 0.0)] * len(
        lyrics_words
    )  # (start, end, confidence)

    for lw_idx, asr_idx in alignment:
        if asr_idx is not None:
            aw = asr_words[asr_idx]
            timestamps[lw_idx] = (aw.start, aw.end, aw.score)

    # Second pass: interpolate unmatched words
    # Build sorted list of matched positions for neighbor lookup
    matched_positions: list[tuple[int, float, float]] = []  # (lw_idx, start, end)
    for lw_idx, asr_idx in alignment:
        if asr_idx is not None:
            aw = asr_words[asr_idx]
            matched_positions.append((lw_idx, aw.start, aw.end))
    matched_positions.sort(key=lambda x: x[0])

    for lw_idx, asr_idx in alignment:
        if asr_idx is not None:
            continue  # already has timestamp

        # Find nearest left and right matched neighbors
        left_match: Optional[tuple[float, float]] = None
        right_match: Optional[tuple[float, float]] = None
        left_pos: Optional[int] = None
        right_pos: Optional[int] = None

        for mp_idx, (mp_lw_idx, mp_start, mp_end) in enumerate(matched_positions):
            if mp_lw_idx < lw_idx:
                left_match = (mp_start, mp_end)
                left_pos = mp_lw_idx
            elif mp_lw_idx > lw_idx:
                right_match = (mp_start, mp_end)
                right_pos = mp_lw_idx
                break

        # Interpolate
        if left_match is None and right_match is None:
            timestamps[lw_idx] = (0.0, 0.0, 0.3)
        elif left_match is None:
            # Before first match
            assert right_match is not None and right_pos is not None
            gap_words = right_pos  # number of words before the right match
            if gap_words > 0:
                slot = right_match[0] / gap_words
                start = lw_idx * slot
                end = start + slot
                timestamps[lw_idx] = (start, min(end, right_match[0]), 0.3)
            else:
                timestamps[lw_idx] = (0.0, 0.0, 0.3)
        elif right_match is None:
            # After last match
            assert left_match is not None and left_pos is not None
            remaining = len(lyrics_words) - left_pos - 1
            pos_in_remaining = lw_idx - left_pos
            if remaining > 0:
                slot = 0.5 / remaining
                start = left_match[1] + (pos_in_remaining - 1) * slot
                end = start + slot
                timestamps[lw_idx] = (max(left_match[1], start), end, 0.3)
            else:
                timestamps[lw_idx] = (left_match[1], left_match[1] + 0.1, 0.3)
        else:
            # Between two matches
            assert left_pos is not None and right_pos is not None
            gap_words = right_pos - left_pos - 1  # unmatched words in gap
            if gap_words > 0:
                pos_in_gap = lw_idx - left_pos  # 1-based position in gap
                span = right_match[0] - left_match[1]
                slot = span / (gap_words + 1)
                start = left_match[1] + pos_in_gap * slot
                end = start + slot
                timestamps[lw_idx] = (start, min(end, right_match[0]), 0.3)
            else:
                mid = (left_match[1] + right_match[0]) / 2
                timestamps[lw_idx] = (mid, mid, 0.3)

    # Group by line
    lines: list[SyncedLine] = []
    for line_idx, line_text in enumerate(lyrics_lines):
        line_word_indices = [
            i for i, w in enumerate(lyrics_words) if w.line_idx == line_idx
        ]
        if not line_word_indices:
            continue

        synced_words: list[SyncedWord] = []
        for wi in line_word_indices:
            start, end, conf = timestamps[wi]
            synced_words.append(
                SyncedWord(
                    text=lyrics_words[wi].word,
                    start=round(start, 4),
                    end=round(end, 4),
                    confidence=round(conf, 4),
                )
            )

        line_start = synced_words[0].start
        line_end = synced_words[-1].end
        lines.append(
            SyncedLine(
                text=line_text.strip(),
                start=line_start,
                end=line_end,
                words=synced_words,
            )
        )

    return lines


def compute_confidence(lines: list[SyncedLine]) -> float:
    """
    Compute overall confidence score from synced lines.

    Per-line confidence = average of word confidences.
    Overall = weighted average by word count per line.
    Returns 0.0 if no lines or no words.
    """
    total_words = 0
    weighted_sum = 0.0

    for line in lines:
        if not line.words:
            continue
        line_conf = sum(w.confidence for w in line.words) / len(line.words)
        word_count = len(line.words)
        weighted_sum += line_conf * word_count
        total_words += word_count

    if total_words == 0:
        return 0.0

    return weighted_sum / total_words
