"""Tests for Demucs vocal separation module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import torch
import torchaudio

from syncer.alignment.demucs_separator import VocalSeparator, SeparationResult


def _make_sine_wav(path: Path, duration: float = 3.0, sr: int = 44100) -> Path:
    """Generate a synthetic sine wave WAV file."""
    t = torch.linspace(0, duration, int(sr * duration))
    wave = torch.sin(2 * 3.14159 * 440 * t).unsqueeze(0)  # (1, samples)
    torchaudio.save(str(path), wave, sr)
    return path


class TestVocalSeparatorInit:
    def test_default_model_name(self):
        sep = VocalSeparator()
        assert sep.model_name == "htdemucs"

    def test_custom_model_name(self):
        sep = VocalSeparator(model_name="htdemucs_ft")
        assert sep.model_name == "htdemucs_ft"

    def test_model_not_loaded_on_init(self):
        sep = VocalSeparator()
        assert sep._model is None


class TestVocalSeparatorSeparate:
    def test_file_not_found(self, tmp_path):
        sep = VocalSeparator()
        with pytest.raises(FileNotFoundError, match="Audio file not found"):
            sep.separate(tmp_path / "nonexistent.wav", tmp_path / "out")

    def test_creates_output_dir(self, tmp_path):
        """Output dir is created if it doesn't exist (tested via mock)."""
        wav = _make_sine_wav(tmp_path / "test.wav")
        output_dir = tmp_path / "nested" / "output"

        # Mock the model to avoid loading real Demucs
        mock_model = MagicMock()
        mock_model.samplerate = 44100
        # apply_model returns (batch=1, sources=4, channels=2, time)
        fake_sources = torch.randn(1, 4, 2, 44100 * 3)

        with (
            patch(
                "syncer.alignment.demucs_separator.get_model", return_value=mock_model
            ),
            patch(
                "syncer.alignment.demucs_separator.apply_model",
                return_value=fake_sources,
            ),
        ):
            result = sep = VocalSeparator()
            result = sep.separate(wav, output_dir)

        assert output_dir.exists()
        assert result == output_dir / "vocals.wav"

    def test_returns_vocals_path(self, tmp_path):
        wav = _make_sine_wav(tmp_path / "test.wav")
        output_dir = tmp_path / "out"

        mock_model = MagicMock()
        mock_model.samplerate = 44100
        fake_sources = torch.randn(1, 4, 2, 44100 * 3)

        with (
            patch(
                "syncer.alignment.demucs_separator.get_model", return_value=mock_model
            ),
            patch(
                "syncer.alignment.demucs_separator.apply_model",
                return_value=fake_sources,
            ),
        ):
            sep = VocalSeparator()
            result = sep.separate(wav, output_dir)

        assert result == output_dir / "vocals.wav"
        assert result.exists()

    def test_vocals_wav_is_valid(self, tmp_path):
        """The output vocals.wav should be loadable by torchaudio."""
        wav = _make_sine_wav(tmp_path / "test.wav")
        output_dir = tmp_path / "out"

        mock_model = MagicMock()
        mock_model.samplerate = 44100
        fake_sources = torch.randn(1, 4, 2, 44100 * 3)

        with (
            patch(
                "syncer.alignment.demucs_separator.get_model", return_value=mock_model
            ),
            patch(
                "syncer.alignment.demucs_separator.apply_model",
                return_value=fake_sources,
            ),
        ):
            sep = VocalSeparator()
            result = sep.separate(wav, output_dir)

        # Verify the output is a valid WAV
        waveform, sr = torchaudio.load(str(result))
        assert sr == 44100
        assert waveform.shape[0] == 2  # stereo
        assert waveform.shape[1] > 0

    def test_resamples_non_44100_input(self, tmp_path):
        """Input at different sample rate gets resampled."""
        # Create WAV at 22050 Hz
        sr = 22050
        t = torch.linspace(0, 3, sr * 3)
        wave = torch.sin(2 * 3.14159 * 440 * t).unsqueeze(0)
        wav = tmp_path / "test_22k.wav"
        torchaudio.save(str(wav), wave, sr)

        output_dir = tmp_path / "out"

        mock_model = MagicMock()
        mock_model.samplerate = 44100
        fake_sources = torch.randn(1, 4, 2, 44100 * 3)

        with (
            patch(
                "syncer.alignment.demucs_separator.get_model", return_value=mock_model
            ),
            patch(
                "syncer.alignment.demucs_separator.apply_model",
                return_value=fake_sources,
            ) as mock_apply,
        ):
            sep = VocalSeparator()
            result = sep.separate(wav, output_dir)

        # Verify apply_model was called (resampling happened internally)
        mock_apply.assert_called_once()
        assert result.exists()

    def test_handles_stereo_input(self, tmp_path):
        """Stereo input is processed correctly."""
        sr = 44100
        t = torch.linspace(0, 3, sr * 3)
        wave = torch.stack(
            [
                torch.sin(2 * 3.14159 * 440 * t),
                torch.sin(2 * 3.14159 * 880 * t),
            ]
        )  # (2, samples)
        wav = tmp_path / "stereo.wav"
        torchaudio.save(str(wav), wave, sr)

        output_dir = tmp_path / "out"
        mock_model = MagicMock()
        mock_model.samplerate = 44100
        fake_sources = torch.randn(1, 4, 2, sr * 3)

        with (
            patch(
                "syncer.alignment.demucs_separator.get_model", return_value=mock_model
            ),
            patch(
                "syncer.alignment.demucs_separator.apply_model",
                return_value=fake_sources,
            ),
        ):
            sep = VocalSeparator()
            result = sep.separate(wav, output_dir)

        assert result.exists()

    def test_runtime_error_on_model_failure(self, tmp_path):
        """RuntimeError from apply_model is wrapped."""
        wav = _make_sine_wav(tmp_path / "test.wav")

        mock_model = MagicMock()
        mock_model.samplerate = 44100

        with (
            patch(
                "syncer.alignment.demucs_separator.get_model", return_value=mock_model
            ),
            patch(
                "syncer.alignment.demucs_separator.apply_model",
                side_effect=RuntimeError("CUDA out of memory"),
            ),
        ):
            sep = VocalSeparator()
            with pytest.raises(RuntimeError, match="Out of memory"):
                sep.separate(wav, tmp_path / "out")

    def test_runtime_error_generic(self, tmp_path):
        """Non-OOM RuntimeError is also wrapped."""
        wav = _make_sine_wav(tmp_path / "test.wav")

        mock_model = MagicMock()
        mock_model.samplerate = 44100

        with (
            patch(
                "syncer.alignment.demucs_separator.get_model", return_value=mock_model
            ),
            patch(
                "syncer.alignment.demucs_separator.apply_model",
                side_effect=RuntimeError("unexpected tensor shape"),
            ),
        ):
            sep = VocalSeparator()
            with pytest.raises(RuntimeError, match="Vocal separation failed"):
                sep.separate(wav, tmp_path / "out")

    def test_memory_cleanup_after_success(self, tmp_path):
        """Model reference is cleared after separation."""
        wav = _make_sine_wav(tmp_path / "test.wav")

        mock_model = MagicMock()
        mock_model.samplerate = 44100
        fake_sources = torch.randn(1, 4, 2, 44100 * 3)

        with (
            patch(
                "syncer.alignment.demucs_separator.get_model", return_value=mock_model
            ),
            patch(
                "syncer.alignment.demucs_separator.apply_model",
                return_value=fake_sources,
            ),
        ):
            sep = VocalSeparator()
            sep.separate(wav, tmp_path / "out")

        # Model should be cleaned up
        assert sep._model is None

    def test_memory_cleanup_after_error(self, tmp_path):
        """Model reference is cleared even on failure."""
        wav = _make_sine_wav(tmp_path / "test.wav")

        mock_model = MagicMock()
        mock_model.samplerate = 44100

        with (
            patch(
                "syncer.alignment.demucs_separator.get_model", return_value=mock_model
            ),
            patch(
                "syncer.alignment.demucs_separator.apply_model",
                side_effect=RuntimeError("boom"),
            ),
        ):
            sep = VocalSeparator()
            with pytest.raises(RuntimeError):
                sep.separate(wav, tmp_path / "out")

        assert sep._model is None


@pytest.mark.slow
class TestVocalSeparatorIntegration:
    """Integration tests that load the real Demucs model. Slow (~30s+)."""

    def test_real_separation(self, tmp_path):
        """End-to-end test with actual Demucs model on synthetic audio."""
        wav = _make_sine_wav(tmp_path / "test.wav", duration=3.0)
        output_dir = tmp_path / "out"

        sep = VocalSeparator()
        result = sep.separate(wav, output_dir)

        assert result == output_dir / "vocals.wav"
        assert result.exists()

        waveform, sr = torchaudio.load(str(result))
        assert sr == 44100
        assert waveform.shape[0] == 2  # stereo output
        assert waveform.shape[1] > 0
