"""Tests for WhisperX word alignment module."""

import pytest
import torch
import torchaudio
from pathlib import Path
from unittest.mock import patch, MagicMock

from syncer.alignment.whisperx_aligner import WordAligner, AlignedWord


# ---------------------------------------------------------------------------
# AlignedWord dataclass tests
# ---------------------------------------------------------------------------


class TestAlignedWord:
    def test_create_with_all_fields(self):
        w = AlignedWord(word="hello", start=0.5, end=1.0, score=0.9)
        assert w.word == "hello"
        assert w.start == 0.5
        assert w.end == 1.0
        assert w.score == 0.9

    def test_score_defaults_to_zero(self):
        w = AlignedWord(word="test", start=0.0, end=0.5)
        assert w.score == 0.0

    def test_is_dataclass(self):
        from dataclasses import is_dataclass

        assert is_dataclass(AlignedWord)


# ---------------------------------------------------------------------------
# Helper: create a silent WAV file
# ---------------------------------------------------------------------------


def _make_silent_wav(
    path: Path, duration_seconds: float = 2.0, sr: int = 16000
) -> Path:
    """Create a short silent WAV file for testing."""
    wave = torch.zeros(1, int(sr * duration_seconds))
    torchaudio.save(str(path), wave, sr)
    return path


# ---------------------------------------------------------------------------
# WordAligner tests (all whisperx calls mocked)
# ---------------------------------------------------------------------------


@patch("syncer.alignment.whisperx_aligner.whisperx")
class TestWordAligner:
    """Tests for WordAligner with fully mocked whisperx."""

    def _setup_mocks(self, mock_whisperx):
        """Configure standard mock returns for whisperx."""
        mock_model = MagicMock()
        mock_whisperx.load_model.return_value = mock_model
        mock_whisperx.load_align_model.return_value = (MagicMock(), MagicMock())
        mock_whisperx.load_audio.return_value = MagicMock()
        return mock_model

    def test_align_returns_words(self, mock_whisperx, tmp_path):
        mock_model = self._setup_mocks(mock_whisperx)
        mock_model.transcribe.return_value = {
            "segments": [
                {
                    "words": [
                        {"word": "hello", "start": 0.5, "end": 1.0, "score": 0.9},
                        {"word": "world", "start": 1.1, "end": 1.5},  # missing score!
                    ]
                }
            ]
        }
        mock_whisperx.align.return_value = mock_model.transcribe.return_value

        audio_path = _make_silent_wav(tmp_path / "test.wav")
        aligner = WordAligner()
        words = aligner.align(audio_path)

        assert len(words) == 2
        assert words[0].word == "hello"
        assert words[0].start == 0.5
        assert words[0].end == 1.0
        assert words[0].score == 0.9
        assert words[1].word == "world"
        assert words[1].start == 1.1
        assert words[1].end == 1.5
        assert words[1].score == 0.0  # default for missing score

    def test_align_empty_segments(self, mock_whisperx, tmp_path):
        """Silent/empty audio returns empty list."""
        mock_model = self._setup_mocks(mock_whisperx)
        mock_model.transcribe.return_value = {"segments": []}

        audio_path = _make_silent_wav(tmp_path / "silent.wav")
        aligner = WordAligner()
        words = aligner.align(audio_path)

        assert words == []
        # align() should NOT be called when segments are empty
        mock_whisperx.align.assert_not_called()

    def test_align_missing_segments_key(self, mock_whisperx, tmp_path):
        """Handles missing 'segments' key in transcription result."""
        mock_model = self._setup_mocks(mock_whisperx)
        mock_model.transcribe.return_value = {}  # no segments key

        audio_path = _make_silent_wav(tmp_path / "empty.wav")
        aligner = WordAligner()
        words = aligner.align(audio_path)

        assert words == []

    def test_align_multi_segment(self, mock_whisperx, tmp_path):
        """Words from multiple segments are combined."""
        mock_model = self._setup_mocks(mock_whisperx)
        mock_model.transcribe.return_value = {
            "segments": [
                {"words": [{"word": "never", "start": 0.0, "end": 0.3, "score": 0.95}]},
                {"words": [{"word": "gonna", "start": 0.4, "end": 0.7, "score": 0.88}]},
            ]
        }
        mock_whisperx.align.return_value = mock_model.transcribe.return_value

        audio_path = _make_silent_wav(tmp_path / "multi.wav")
        aligner = WordAligner()
        words = aligner.align(audio_path)

        assert len(words) == 2
        assert words[0].word == "never"
        assert words[1].word == "gonna"

    def test_align_segment_without_words(self, mock_whisperx, tmp_path):
        """Segments without 'words' key are handled gracefully."""
        mock_model = self._setup_mocks(mock_whisperx)
        mock_model.transcribe.return_value = {
            "segments": [
                {"text": "some text but no words array"},  # no "words" key
                {"words": [{"word": "ok", "start": 1.0, "end": 1.5, "score": 0.8}]},
            ]
        }
        mock_whisperx.align.return_value = mock_model.transcribe.return_value

        audio_path = _make_silent_wav(tmp_path / "partial.wav")
        aligner = WordAligner()
        words = aligner.align(audio_path)

        assert len(words) == 1
        assert words[0].word == "ok"

    def test_align_missing_start_end(self, mock_whisperx, tmp_path):
        """Words with missing start/end default to 0.0."""
        mock_model = self._setup_mocks(mock_whisperx)
        mock_model.transcribe.return_value = {
            "segments": [
                {
                    "words": [
                        {"word": "partial"},  # missing start, end, score
                    ]
                }
            ]
        }
        mock_whisperx.align.return_value = mock_model.transcribe.return_value

        audio_path = _make_silent_wav(tmp_path / "missing.wav")
        aligner = WordAligner()
        words = aligner.align(audio_path)

        assert len(words) == 1
        assert words[0].word == "partial"
        assert words[0].start == 0.0
        assert words[0].end == 0.0
        assert words[0].score == 0.0

    def test_init_loads_models(self, mock_whisperx):
        """Constructor loads both transcription and alignment models."""
        mock_whisperx.load_model.return_value = MagicMock()
        mock_whisperx.load_align_model.return_value = (MagicMock(), MagicMock())

        aligner = WordAligner(
            model_name="large-v2", device="cpu", compute_type="float32"
        )

        mock_whisperx.load_model.assert_called_once_with(
            "large-v2", "cpu", compute_type="float32"
        )
        mock_whisperx.load_align_model.assert_called_once_with(
            language_code="en", device="cpu"
        )
        assert aligner.device == "cpu"

    def test_align_calls_whisperx_correctly(self, mock_whisperx, tmp_path):
        """Verify correct whisperx API call sequence."""
        mock_model = self._setup_mocks(mock_whisperx)
        segments = [
            {"words": [{"word": "test", "start": 0.0, "end": 0.5, "score": 1.0}]}
        ]
        mock_model.transcribe.return_value = {"segments": segments}
        mock_whisperx.align.return_value = {"segments": segments}
        mock_audio = MagicMock()
        mock_whisperx.load_audio.return_value = mock_audio

        audio_path = _make_silent_wav(tmp_path / "api.wav")
        aligner = WordAligner()
        aligner.align(audio_path)

        # Verify API call sequence
        mock_whisperx.load_audio.assert_called_once_with(str(audio_path))
        mock_model.transcribe.assert_called_once_with(mock_audio, batch_size=8)
        mock_whisperx.align.assert_called_once_with(
            segments,
            aligner.align_model,
            aligner.align_metadata,
            mock_audio,
            "cpu",
        )

    def test_accepts_path_as_string(self, mock_whisperx, tmp_path):
        """align() accepts string paths, not just Path objects."""
        mock_model = self._setup_mocks(mock_whisperx)
        mock_model.transcribe.return_value = {"segments": []}

        audio_path = _make_silent_wav(tmp_path / "str_path.wav")
        aligner = WordAligner()
        words = aligner.align(str(audio_path))  # pass as string

        assert words == []


# ---------------------------------------------------------------------------
# Slow integration test (loads real model — deselect with -m "not slow")
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_real_whisperx_silent_audio(tmp_path):
    """Integration test: real WhisperX on silent audio produces empty or near-empty output."""
    audio_path = _make_silent_wav(tmp_path / "silent.wav", duration_seconds=3.0)
    aligner = WordAligner(model_name="base", device="cpu", compute_type="float32")
    words = aligner.align(audio_path)
    # Silent audio should produce zero or very few spurious words
    assert len(words) <= 5  # generous threshold for silence detection
