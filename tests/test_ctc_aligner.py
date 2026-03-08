"""Tests for CTC forced alignment using torchaudio MMS_FA bundle."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import torch


# ---------------------------------------------------------------------------
# Group 1: Class structure
# ---------------------------------------------------------------------------


class TestCTCAlignerStructure:
    def test_ctc_aligner_instantiates(self):
        from syncer.alignment.ctc_aligner import CTCAligner

        a = CTCAligner()
        assert a is not None

    def test_ctc_aligner_no_model_on_init(self):
        """Lazy loading — model should NOT be loaded at __init__ time."""
        from syncer.alignment.ctc_aligner import CTCAligner

        a = CTCAligner(device="cpu")
        assert a._model is None  # lazy — not loaded yet

    def test_ctc_aligner_custom_device(self):
        from syncer.alignment.ctc_aligner import CTCAligner

        a = CTCAligner(device="cpu")
        assert a.device == "cpu"


# ---------------------------------------------------------------------------
# Group 2: Dataclasses
# ---------------------------------------------------------------------------


class TestDataclasses:
    def test_aligned_word_dataclass(self):
        """AlignedWord has word, start, end, score fields."""
        from syncer.alignment.ctc_aligner import AlignedWord

        w = AlignedWord(word="hello", start=0.5, end=1.2, score=0.9)
        assert w.word == "hello"
        assert w.start == 0.5
        assert w.end == 1.2
        assert w.score == 0.9

    def test_aligned_word_default_score(self):
        """AlignedWord score defaults to 0.0."""
        from syncer.alignment.ctc_aligner import AlignedWord

        w = AlignedWord(word="test", start=0.0, end=1.0)
        assert w.score == 0.0

    def test_alignment_result_dataclass(self):
        """AlignmentResult has words and detected_language."""
        from syncer.alignment.ctc_aligner import AlignedWord, AlignmentResult

        r = AlignmentResult(words=[], detected_language=None)
        assert r.words == []
        assert r.detected_language is None

    def test_alignment_result_with_language(self):
        from syncer.alignment.ctc_aligner import AlignmentResult

        r = AlignmentResult(words=[], detected_language="hi")
        assert r.detected_language == "hi"


# ---------------------------------------------------------------------------
# Helpers for mocking the MMS_FA bundle
# ---------------------------------------------------------------------------


def _make_mock_bundle(num_words: int = 2):
    """Create a fully mocked MMS_FA bundle with consistent fake data.

    Returns (mock_bundle, expected_word_count) where expected_word_count
    is the number of AlignedWord objects the aligner should produce.
    """
    # Model: waveform → (emission, None)
    # emission shape: (batch=1, frames=49, tokens=29) for ~1s audio
    fake_emission = torch.randn(1, 49, 29)
    mock_model = MagicMock()
    mock_model.return_value = (fake_emission, None)
    mock_model.to = MagicMock(return_value=mock_model)  # .to(device) returns self

    # Tokenizer: list[str] → list[list[int]]
    mock_tokenizer = MagicMock()
    mock_tokenizer.return_value = [[15, 3, 12, 12, 5], [19, 5, 9, 12, 13]][:num_words]

    # Aligner: (emission, tokens) → list[list[TokenSpan]]
    def make_span(start, end, score=0.85):
        span = MagicMock()
        span.start = start
        span.end = end
        span.score = score
        return span

    fake_word_spans = [
        [make_span(2, 8, 0.9), make_span(9, 14, 0.85)],  # "hello" chars
        [make_span(16, 22, 0.8), make_span(23, 28, 0.75)],  # "world" chars
    ][:num_words]

    mock_aligner = MagicMock()
    mock_aligner.return_value = fake_word_spans

    mock_bundle = MagicMock()
    mock_bundle.get_model.return_value = mock_model
    mock_bundle.get_tokenizer.return_value = mock_tokenizer
    mock_bundle.get_aligner.return_value = mock_aligner
    mock_bundle.sample_rate = 16000

    return mock_bundle


# ---------------------------------------------------------------------------
# Group 3: align() with fully mocked torchaudio
# ---------------------------------------------------------------------------


class TestAlignMethod:
    def test_align_returns_alignment_result(self):
        """align() returns AlignmentResult with words and detected_language."""
        from syncer.alignment.ctc_aligner import (
            AlignedWord,
            AlignmentResult,
            CTCAligner,
        )

        aligner = CTCAligner(device="cpu")
        mock_bundle = _make_mock_bundle(num_words=2)
        fake_waveform = torch.zeros(1, 16000)  # 1s mono at 16kHz

        with (
            patch("torchaudio.load", return_value=(fake_waveform, 16000)),
            patch("torchaudio.pipelines.MMS_FA", mock_bundle),
            patch(
                "syncer.alignment.ctc_aligner.normalize_for_alignment",
                return_value=["hello", "world"],
            ),
        ):
            result = aligner.align(
                Path("/fake/audio.wav"), ["hello world"], language=None
            )

        assert isinstance(result, AlignmentResult)
        assert isinstance(result.words, list)
        assert len(result.words) == 2
        assert all(isinstance(w, AlignedWord) for w in result.words)
        assert result.detected_language is None

    def test_align_passes_language(self):
        """detected_language in result matches the language parameter."""
        from syncer.alignment.ctc_aligner import CTCAligner

        aligner = CTCAligner(device="cpu")
        mock_bundle = _make_mock_bundle(num_words=1)
        fake_waveform = torch.zeros(1, 16000)

        with (
            patch("torchaudio.load", return_value=(fake_waveform, 16000)),
            patch("torchaudio.pipelines.MMS_FA", mock_bundle),
            patch(
                "syncer.alignment.ctc_aligner.normalize_for_alignment",
                return_value=["namaste"],
            ),
        ):
            result = aligner.align(Path("/fake/audio.wav"), ["namaste"], language="hi")

        assert result.detected_language == "hi"

    def test_align_empty_lyrics_returns_empty(self):
        """Empty lyrics list → empty word list, no crash."""
        from syncer.alignment.ctc_aligner import AlignmentResult, CTCAligner

        aligner = CTCAligner(device="cpu")

        # No need to mock bundle — should short-circuit before model load
        with patch("torchaudio.load", return_value=(torch.zeros(1, 16000), 16000)):
            result = aligner.align(Path("/fake/audio.wav"), [], language=None)

        assert isinstance(result, AlignmentResult)
        assert result.words == []

    def test_align_resamples_audio(self):
        """Stereo 44100Hz audio gets resampled to mono 16kHz."""
        from syncer.alignment.ctc_aligner import CTCAligner

        aligner = CTCAligner(device="cpu")
        mock_bundle = _make_mock_bundle(num_words=1)
        # Stereo 44100Hz waveform
        fake_waveform = torch.zeros(2, 44100)

        mock_resampler = MagicMock()
        mock_resampler.return_value = torch.zeros(1, 16000)

        with (
            patch("torchaudio.load", return_value=(fake_waveform, 44100)),
            patch("torchaudio.pipelines.MMS_FA", mock_bundle),
            patch(
                "torchaudio.transforms.Resample", return_value=mock_resampler
            ) as mock_resample_cls,
            patch(
                "syncer.alignment.ctc_aligner.normalize_for_alignment",
                return_value=["hello"],
            ),
        ):
            result = aligner.align(Path("/fake/audio.wav"), ["hello"], language=None)

        # Verify Resample was created with correct frequencies
        mock_resample_cls.assert_called_once_with(orig_freq=44100, new_freq=16000)
        # Verify resampler was called
        mock_resampler.assert_called_once()
        assert len(result.words) == 1

    def test_align_word_timestamps_are_floats(self):
        """AlignedWord.start and .end are float seconds, not frame indices."""
        from syncer.alignment.ctc_aligner import CTCAligner

        aligner = CTCAligner(device="cpu")
        mock_bundle = _make_mock_bundle(num_words=1)
        fake_waveform = torch.zeros(1, 16000)

        with (
            patch("torchaudio.load", return_value=(fake_waveform, 16000)),
            patch("torchaudio.pipelines.MMS_FA", mock_bundle),
            patch(
                "syncer.alignment.ctc_aligner.normalize_for_alignment",
                return_value=["hello"],
            ),
        ):
            result = aligner.align(Path("/fake/audio.wav"), ["hello"], language=None)

        word = result.words[0]
        assert isinstance(word.start, float)
        assert isinstance(word.end, float)
        # Frame 2 * 320 / 16000 = 0.04s, Frame 14 * 320 / 16000 = 0.28s
        assert word.start == pytest.approx(2 * 320 / 16000)
        assert word.end == pytest.approx(14 * 320 / 16000)

    def test_align_word_scores_averaged(self):
        """AlignedWord.score is the average of character-level span scores."""
        from syncer.alignment.ctc_aligner import CTCAligner

        aligner = CTCAligner(device="cpu")
        mock_bundle = _make_mock_bundle(num_words=1)
        fake_waveform = torch.zeros(1, 16000)

        with (
            patch("torchaudio.load", return_value=(fake_waveform, 16000)),
            patch("torchaudio.pipelines.MMS_FA", mock_bundle),
            patch(
                "syncer.alignment.ctc_aligner.normalize_for_alignment",
                return_value=["hello"],
            ),
        ):
            result = aligner.align(Path("/fake/audio.wav"), ["hello"], language=None)

        word = result.words[0]
        # First word spans have scores 0.9 and 0.85 → avg = 0.875
        assert word.score == pytest.approx(0.875)

    def test_align_lazy_loads_model(self):
        """Model is loaded on first align() call, not on __init__."""
        from syncer.alignment.ctc_aligner import CTCAligner

        aligner = CTCAligner(device="cpu")
        assert aligner._model is None

        mock_bundle = _make_mock_bundle(num_words=1)
        fake_waveform = torch.zeros(1, 16000)

        with (
            patch("torchaudio.load", return_value=(fake_waveform, 16000)),
            patch("torchaudio.pipelines.MMS_FA", mock_bundle),
            patch(
                "syncer.alignment.ctc_aligner.normalize_for_alignment",
                return_value=["hello"],
            ),
        ):
            aligner.align(Path("/fake/audio.wav"), ["hello"], language=None)

        # After align, model should be loaded
        assert aligner._model is not None

    def test_align_converts_stereo_to_mono(self):
        """Stereo waveform is averaged to mono before processing."""
        from syncer.alignment.ctc_aligner import CTCAligner

        aligner = CTCAligner(device="cpu")
        mock_bundle = _make_mock_bundle(num_words=1)
        # Stereo 16kHz — same sample rate, so no resample needed
        fake_waveform = torch.ones(2, 16000)  # stereo

        with (
            patch("torchaudio.load", return_value=(fake_waveform, 16000)),
            patch("torchaudio.pipelines.MMS_FA", mock_bundle),
            patch(
                "syncer.alignment.ctc_aligner.normalize_for_alignment",
                return_value=["hello"],
            ),
        ):
            result = aligner.align(Path("/fake/audio.wav"), ["hello"], language=None)

        # Model should have been called with mono (1 channel)
        model_call_args = mock_bundle.get_model.return_value.call_args
        input_waveform = model_call_args[0][0]
        assert input_waveform.shape[0] == 1  # mono


# ---------------------------------------------------------------------------
# Group 4: normalize_for_alignment integration
# ---------------------------------------------------------------------------


class TestNormalizationIntegration:
    def test_align_calls_normalize_for_alignment(self):
        """normalize_for_alignment() is called on each lyrics line before tokenization."""
        from syncer.alignment.ctc_aligner import CTCAligner

        aligner = CTCAligner(device="cpu")
        mock_bundle = _make_mock_bundle(num_words=2)
        fake_waveform = torch.zeros(1, 16000)

        with (
            patch("torchaudio.load", return_value=(fake_waveform, 16000)),
            patch("torchaudio.pipelines.MMS_FA", mock_bundle),
            patch("syncer.alignment.ctc_aligner.normalize_for_alignment") as mock_norm,
        ):
            mock_norm.return_value = ["hello", "world"]
            aligner.align(
                Path("/fake/audio.wav"),
                ["Hello, World!"],
                language=None,
            )

        mock_norm.assert_called_once_with("Hello, World!")

    def test_align_calls_normalize_per_line(self):
        """Each lyrics line gets its own normalize_for_alignment() call."""
        from syncer.alignment.ctc_aligner import CTCAligner

        aligner = CTCAligner(device="cpu")
        mock_bundle = _make_mock_bundle(num_words=2)
        fake_waveform = torch.zeros(1, 16000)

        with (
            patch("torchaudio.load", return_value=(fake_waveform, 16000)),
            patch("torchaudio.pipelines.MMS_FA", mock_bundle),
            patch("syncer.alignment.ctc_aligner.normalize_for_alignment") as mock_norm,
        ):
            mock_norm.side_effect = [["hello"], ["world"]]
            aligner.align(
                Path("/fake/audio.wav"),
                ["Hello!", "World!"],
                language=None,
            )

        assert mock_norm.call_count == 2
        mock_norm.assert_any_call("Hello!")
        mock_norm.assert_any_call("World!")

    def test_align_normalize_returns_empty_skips_gracefully(self):
        """If normalize returns empty words for all lines, result is empty."""
        from syncer.alignment.ctc_aligner import CTCAligner

        aligner = CTCAligner(device="cpu")

        with (
            patch("torchaudio.load", return_value=(torch.zeros(1, 16000), 16000)),
            patch(
                "syncer.alignment.ctc_aligner.normalize_for_alignment",
                return_value=[],
            ),
        ):
            result = aligner.align(
                Path("/fake/audio.wav"),
                ["!!!"],  # normalizes to empty
                language=None,
            )

        assert result.words == []
