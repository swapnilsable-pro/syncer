from syncer.models import SyncedLine


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
