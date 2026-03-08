"""Text normalization for CTC forced alignment via torchaudio MMS_FA."""

import logging
import re
from functools import lru_cache

logger = logging.getLogger(__name__)

# Track if we've already warned about uroman being unavailable
_uroman_warned = False

# Regex: keep only a-z, apostrophe, and whitespace (hyphens replaced with spaces)
_STRIP_PATTERN = re.compile(r"[^a-z'\s]")

# Regex: digits
_DIGIT_PATTERN = re.compile(r"[0-9]")


@lru_cache(maxsize=1)
def _get_uroman_instance():
    """Lazy-load uroman. Returns Uroman instance or None if unavailable.

    Cached so we only attempt the import once.
    """
    global _uroman_warned
    try:
        from uroman import Uroman

        return Uroman()
    except (ImportError, Exception) as e:
        if not _uroman_warned:
            logger.warning("uroman not available: romanization skipped (%s)", e)
            _uroman_warned = True
        return None


def romanize(text: str) -> str:
    """Romanize non-Latin text to ASCII via uroman.

    Args:
        text: Input text, possibly containing non-Latin scripts.

    Returns:
        Romanized ASCII string. If uroman is unavailable, returns
        the original text unchanged.
    """
    if not text:
        return ""

    # Fast path: if all chars are ASCII letters or common punctuation/spaces,
    # no romanization needed
    lower = text.lower()
    if all(c.isascii() for c in lower):
        return text

    # Try uroman
    uroman_instance = _get_uroman_instance()
    if uroman_instance is not None:
        try:
            return uroman_instance.romanize_string(text)
        except Exception as e:
            logger.warning("uroman romanization failed: %s", e)
            return text

    return text


def normalize_for_alignment(text: str) -> list[str]:
    """Normalize raw lyrics line to safe word list for MMS_FA tokenizer.

    The MMS_FA tokenizer only accepts: a-z, apostrophe ('), and space. Hyphens
    map to the blank token (index 0) and must be replaced with spaces. Any other
    character causes a KeyError crash.

    Args:
        text: Raw lyrics line (may contain punctuation, digits, mixed case).

    Returns:
        List of clean lowercase words safe for the MMS_FA tokenizer.
        Empty list if input is empty or produces no valid words.
    """
    if not text or not text.strip():
        return []

    # Step 1: Romanize non-Latin scripts
    text = romanize(text)

    # Step 2: Lowercase
    text = text.lower()

    # Step 3: Remove digits
    text = _DIGIT_PATTERN.sub("", text)

    # Step 3.5: Replace hyphens with spaces (hyphen maps to blank token index 0 in MMS_FA)
    text = text.replace("-", " ")

    # Step 4: Strip all characters except a-z, apostrophe, whitespace
    text = _STRIP_PATTERN.sub("", text)

    # Step 5: Split on whitespace, strip each token, drop empties
    words = [w.strip() for w in text.split()]
    words = [w for w in words if w]

    return words
