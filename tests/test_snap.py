"""Tests for snap-to-lyrics text matching and confidence scoring."""

import pytest

from syncer.alignment.snap import (
    AlignedWord,
    snap_words_to_lyrics,
    compute_confidence,
)


# --- Perfect alignment ---


def test_perfect_alignment():
    """ASR matches lyrics exactly — all words get correct timestamps."""
    asr = [
        AlignedWord("hello", 1.0, 1.5, 0.95),
        AlignedWord("world", 1.6, 2.0, 0.90),
    ]
    lines = snap_words_to_lyrics(asr, ["hello world"])
    assert len(lines) == 1
    assert lines[0].start == 1.0
    assert lines[0].end == 2.0
    assert len(lines[0].words) == 2
    assert lines[0].words[0].text == "hello"
    assert lines[0].words[0].start == 1.0
    assert lines[0].words[0].end == 1.5
    assert lines[0].words[0].confidence > 0.9
    assert lines[0].words[1].text == "world"
    assert lines[0].words[1].start == 1.6
    assert lines[0].words[1].end == 2.0
    assert lines[0].words[1].confidence > 0.8


def test_perfect_alignment_case_insensitive():
    """Case differences should still match exactly."""
    asr = [
        AlignedWord("Hello", 1.0, 1.5, 0.95),
        AlignedWord("WORLD", 1.6, 2.0, 0.90),
    ]
    lines = snap_words_to_lyrics(asr, ["hello world"])
    assert len(lines) == 1
    assert lines[0].words[0].confidence > 0.9
    assert lines[0].words[1].confidence > 0.8


# --- Fuzzy matching ---


def test_fuzzy_match():
    """'helo' should match 'hello' via Levenshtein ratio > 0.7."""
    asr = [
        AlignedWord("helo", 1.0, 1.5, 0.8),
        AlignedWord("world", 1.6, 2.0, 0.9),
    ]
    lines = snap_words_to_lyrics(asr, ["hello world"])
    assert len(lines) == 1
    assert len(lines[0].words) == 2
    # Both words should get timestamps from ASR
    assert lines[0].words[0].start > 0
    assert lines[0].words[1].start > 0


def test_fuzzy_match_threshold():
    """Words with ratio <= 0.7 should not match."""
    # "ab" vs "xyz" has ratio 0.0 — no match
    asr = [AlignedWord("xyz", 1.0, 1.5, 0.8)]
    lines = snap_words_to_lyrics(asr, ["abcdef"])
    assert len(lines) == 1
    # Word should be unmatched (interpolated, confidence 0.3)
    assert lines[0].words[0].confidence <= 0.3


# --- Empty inputs ---


def test_empty_asr():
    """Empty ASR words: return lines with 0 timestamps and confidence 0."""
    lines = snap_words_to_lyrics([], ["hello world"])
    assert len(lines) == 1
    assert lines[0].words[0].start == 0.0
    assert lines[0].words[0].end == 0.0
    assert lines[0].words[0].confidence == 0.0
    assert lines[0].words[1].start == 0.0
    assert lines[0].words[1].confidence == 0.0


def test_empty_lyrics():
    """Empty lyrics: return empty list."""
    asr = [AlignedWord("hello", 1.0, 1.5, 0.9)]
    lines = snap_words_to_lyrics(asr, [])
    assert lines == []


def test_empty_both():
    """Both empty: return empty list."""
    lines = snap_words_to_lyrics([], [])
    assert lines == []


# --- Multiline ---


def test_multiline():
    """Multiple lyrics lines get separate SyncedLine objects with correct timestamps."""
    asr = [
        AlignedWord("never", 1.0, 1.3, 0.9),
        AlignedWord("gonna", 1.4, 1.7, 0.9),
        AlignedWord("give", 2.0, 2.3, 0.9),
        AlignedWord("you", 2.4, 2.6, 0.9),
        AlignedWord("up", 2.7, 3.0, 0.9),
    ]
    lines = snap_words_to_lyrics(asr, ["never gonna", "give you up"])
    assert len(lines) == 2
    assert lines[0].text == "never gonna"
    assert lines[0].start == 1.0
    assert lines[0].end == 1.7
    assert lines[1].text == "give you up"
    assert lines[1].start == 2.0
    assert lines[1].end == 3.0


def test_three_lines():
    """Three-line lyrics alignment."""
    asr = [
        AlignedWord("a", 0.5, 0.7, 0.9),
        AlignedWord("b", 1.0, 1.2, 0.9),
        AlignedWord("c", 1.5, 1.7, 0.9),
    ]
    lines = snap_words_to_lyrics(asr, ["a", "b", "c"])
    assert len(lines) == 3
    assert lines[0].start == 0.5
    assert lines[1].start == 1.0
    assert lines[2].start == 1.5


# --- Single word ---


def test_single_word_lyrics():
    """Single word lyrics should work."""
    asr = [AlignedWord("hello", 1.0, 1.5, 0.95)]
    lines = snap_words_to_lyrics(asr, ["hello"])
    assert len(lines) == 1
    assert len(lines[0].words) == 1
    assert lines[0].words[0].text == "hello"
    assert lines[0].start == 1.0
    assert lines[0].end == 1.5


# --- Interpolation ---


def test_unmatched_word_interpolated():
    """Words not in ASR get interpolated timestamps with low confidence."""
    # ASR has "hello" and "world" but lyrics have "hello beautiful world"
    asr = [
        AlignedWord("hello", 1.0, 1.5, 0.9),
        AlignedWord("world", 3.0, 3.5, 0.9),
    ]
    lines = snap_words_to_lyrics(asr, ["hello beautiful world"])
    assert len(lines) == 1
    assert len(lines[0].words) == 3
    # "hello" matched
    assert lines[0].words[0].confidence > 0.5
    # "beautiful" interpolated
    assert lines[0].words[1].confidence == 0.3
    assert lines[0].words[1].start > 1.0  # after "hello"
    assert lines[0].words[1].end < 3.5  # before "world" end
    # "world" matched
    assert lines[0].words[2].confidence > 0.5


# --- Extra ASR words ---


def test_extra_asr_words_ignored():
    """ASR has more words than lyrics — extra words should be ignored."""
    asr = [
        AlignedWord("oh", 0.5, 0.8, 0.7),
        AlignedWord("hello", 1.0, 1.5, 0.9),
        AlignedWord("world", 1.6, 2.0, 0.9),
        AlignedWord("yeah", 2.1, 2.4, 0.7),
    ]
    lines = snap_words_to_lyrics(asr, ["hello world"])
    assert len(lines) == 1
    assert len(lines[0].words) == 2
    assert lines[0].words[0].text == "hello"
    assert lines[0].words[1].text == "world"


# --- Confidence scoring ---


def test_confidence_scoring():
    """All matched words -> high confidence."""
    asr = [AlignedWord("hello", 1.0, 1.5, 0.95)]
    lines = snap_words_to_lyrics(asr, ["hello"])
    conf = compute_confidence(lines)
    assert conf > 0.9


def test_confidence_empty_lines():
    """No lines -> confidence 0."""
    assert compute_confidence([]) == 0.0


def test_confidence_mixed():
    """Mix of matched and interpolated words gives moderate confidence."""
    asr = [
        AlignedWord("hello", 1.0, 1.5, 0.9),
        AlignedWord("world", 3.0, 3.5, 0.9),
    ]
    lines = snap_words_to_lyrics(asr, ["hello beautiful world"])
    conf = compute_confidence(lines)
    # 2 matched (0.9) + 1 interpolated (0.3) -> ~0.7
    assert 0.5 < conf < 0.95


def test_confidence_no_match():
    """Empty ASR -> confidence 0."""
    lines = snap_words_to_lyrics([], ["hello world"])
    conf = compute_confidence(lines)
    assert conf == 0.0


def test_confidence_multiline_weighted():
    """Confidence is weighted by word count per line."""
    asr = [
        AlignedWord("a", 1.0, 1.2, 1.0),
        AlignedWord("b", 1.3, 1.5, 1.0),
        AlignedWord("c", 1.6, 1.8, 1.0),
        AlignedWord("d", 2.0, 2.2, 0.5),
    ]
    lines = snap_words_to_lyrics(asr, ["a b c", "d"])
    conf = compute_confidence(lines)
    # Line 1: 3 words avg 1.0, Line 2: 1 word avg 0.5
    # Weighted: (3*1.0 + 1*0.5) / 4 = 0.875
    assert abs(conf - 0.875) < 0.01


# --- Line text preservation ---


def test_line_text_preserved():
    """SyncedLine.text should be the original lyrics line text."""
    asr = [
        AlignedWord("hello", 1.0, 1.5, 0.9),
        AlignedWord("world", 1.6, 2.0, 0.9),
    ]
    lines = snap_words_to_lyrics(asr, ["hello world"])
    assert lines[0].text == "hello world"


# --- Word order ---


def test_word_order_preserved():
    """Words in SyncedLine should follow lyrics order, not ASR order."""
    asr = [
        AlignedWord("world", 1.0, 1.5, 0.9),
        AlignedWord("hello", 1.6, 2.0, 0.9),
    ]
    lines = snap_words_to_lyrics(asr, ["hello world"])
    assert lines[0].words[0].text == "hello"
    assert lines[0].words[1].text == "world"
