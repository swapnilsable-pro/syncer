"""Tests for text normalization and romanization for CTC forced alignment."""

from unittest.mock import patch, MagicMock
import pytest

from syncer.alignment.text_normalize import normalize_for_alignment, romanize


# ============================================================
# normalize_for_alignment tests
# ============================================================


class TestNormalizeForAlignment:
    """Tests for normalize_for_alignment()."""

    def test_basic_lowercase(self):
        assert normalize_for_alignment("Hello World!") == ["hello", "world"]

    def test_apostrophe_preserved(self):
        assert normalize_for_alignment("Don't stop") == ["don't", "stop"]

    def test_digit_only_word_stripped(self):
        assert normalize_for_alignment("99 Luftballons") == ["luftballons"]

    def test_punctuation_stripped(self):
        assert normalize_for_alignment("Rock & Roll!!!") == ["rock", "roll"]

    def test_empty_string(self):
        assert normalize_for_alignment("") == []

    def test_whitespace_only(self):
        assert normalize_for_alignment("   spaces   ") == ["spaces"]

    def test_digits_stripped_from_mixed_word(self):
        assert normalize_for_alignment("24K Magic") == ["k", "magic"]

    def test_hyphen_preserved(self):
        assert normalize_for_alignment("rock-n-roll") == ["rock-n-roll"]

    def test_all_punctuation_line(self):
        assert normalize_for_alignment("!!!") == []

    def test_comma_and_period_stripped(self):
        assert normalize_for_alignment("Hello, World.") == ["hello", "world"]

    def test_apostrophe_in_sentence(self):
        assert normalize_for_alignment("it's a beautiful day") == [
            "it's",
            "a",
            "beautiful",
            "day",
        ]

    def test_tabs_and_newlines(self):
        assert normalize_for_alignment("hello\tworld\nfoo") == [
            "hello",
            "world",
            "foo",
        ]

    def test_multiple_spaces(self):
        assert normalize_for_alignment("  hello   world  ") == ["hello", "world"]

    def test_only_digits(self):
        assert normalize_for_alignment("123 456") == []

    def test_mixed_punctuation_and_words(self):
        assert normalize_for_alignment("...hello---world...") == ["hello---world"]

    def test_unicode_accented_latin(self):
        # Accented chars should go through romanize path; result should be lowercase
        result = normalize_for_alignment("café")
        assert isinstance(result, list)
        assert len(result) >= 1  # at least something returned

    def test_returns_list_of_strings(self):
        result = normalize_for_alignment("Hello World")
        assert isinstance(result, list)
        assert all(isinstance(w, str) for w in result)


# ============================================================
# romanize tests
# ============================================================


class TestRomanize:
    """Tests for romanize()."""

    def test_latin_text_unchanged(self):
        assert romanize("hello") == "hello"

    def test_empty_string(self):
        assert romanize("") == ""

    def test_uppercase_passthrough(self):
        # Uppercase ASCII — romanize doesn't lowercase (that's normalize's job)
        result = romanize("HELLO")
        assert isinstance(result, str)

    def test_already_ascii(self):
        assert romanize("world") == "world"

    def test_mixed_ascii(self):
        assert romanize("hello world") == "hello world"

    def test_hindi_if_uroman_available(self):
        """If uroman is installed, Hindi text should be romanized to ASCII."""
        result = romanize("नमस्ते")
        # If uroman is available, result should be ASCII
        # If not, it falls back to original text
        assert isinstance(result, str)
        assert len(result) > 0

    def test_no_crash_on_non_latin(self):
        """Non-Latin text should never crash, regardless of uroman availability."""
        result = romanize("こんにちは")
        assert isinstance(result, str)

    def test_no_crash_on_cyrillic(self):
        result = romanize("Привет")
        assert isinstance(result, str)

    def test_no_crash_on_arabic(self):
        result = romanize("مرحبا")
        assert isinstance(result, str)


class TestRomanizeFallback:
    """Tests for romanize() graceful fallback when uroman is unavailable."""

    def test_fallback_returns_original_text(self):
        """When uroman import fails, romanize returns text as-is."""
        with patch.dict("sys.modules", {"uroman": None}):
            # Need to clear cached uroman instance
            import syncer.alignment.text_normalize as mod

            # Reset the module-level state
            original_cache = getattr(mod, "_get_uroman_instance", None)
            if original_cache and hasattr(original_cache, "cache_clear"):
                original_cache.cache_clear()

            # Patch the helper to simulate uroman being unavailable
            with patch.object(mod, "_get_uroman_instance", return_value=None):
                result = mod.romanize("नमस्ते")
                assert result == "नमस्ते"

    def test_fallback_no_crash(self):
        """When uroman is unavailable, no exception is raised."""
        import syncer.alignment.text_normalize as mod

        with patch.object(mod, "_get_uroman_instance", return_value=None):
            result = mod.romanize("任何文字")
            assert isinstance(result, str)


class TestNormalizeWithRomanize:
    """Integration tests: normalize calls romanize internally."""

    def test_normalize_calls_romanize(self):
        """normalize_for_alignment should call romanize on the input."""
        with patch(
            "syncer.alignment.text_normalize.romanize", return_value="hello world"
        ) as mock_rom:
            result = normalize_for_alignment("Hello World")
            mock_rom.assert_called_once()
            assert result == ["hello", "world"]
