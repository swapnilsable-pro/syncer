"""Demucs vocal isolation module using htdemucs model."""

import gc
import logging
from dataclasses import dataclass
from pathlib import Path

import torch
import torchaudio
from demucs.apply import apply_model
from demucs.pretrained import get_model

logger = logging.getLogger(__name__)

# Source index mapping for htdemucs output
_VOCALS_INDEX = 3  # ['drums', 'bass', 'other', 'vocals']


@dataclass
class SeparationResult:
    """Result of vocal separation."""

    vocals_path: Path
    sample_rate: int
    duration: float  # seconds


class VocalSeparator:
    """Isolates vocals from a mixed audio file using Demucs.

    Uses the lower-level Demucs API (get_model + apply_model)
    compatible with Demucs 4.0.1.
    """

    def __init__(self, model_name: str = "htdemucs") -> None:
        self.model_name = model_name
        self._model = None

    def _load_model(self):
        """Lazy-load the Demucs model."""
        if self._model is None:
            logger.info("Loading Demucs model: %s", self.model_name)
            self._model = get_model(self.model_name)
        return self._model

    def separate(self, audio_path: Path, output_dir: Path) -> Path:
        """Separate vocals from a mixed audio file.

        Args:
            audio_path: Path to input audio file (WAV, MP3, etc.)
            output_dir: Directory to write vocals.wav

        Returns:
            Path to the extracted vocals.wav file

        Raises:
            FileNotFoundError: If audio_path does not exist
            RuntimeError: If separation fails (e.g., OOM, invalid audio)
        """
        audio_path = Path(audio_path)
        output_dir = Path(output_dir)

        if not audio_path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        output_dir.mkdir(parents=True, exist_ok=True)
        vocals_path = output_dir / "vocals.wav"

        model = None
        sources = None
        try:
            model = self._load_model()

            # Load audio
            logger.info("Loading audio: %s", audio_path)
            waveform, sr = torchaudio.load(str(audio_path))

            # Resample to model's expected sample rate (44100 Hz)
            if sr != model.samplerate:
                logger.info("Resampling from %d to %d Hz", sr, model.samplerate)
                waveform = torchaudio.functional.resample(
                    waveform, sr, model.samplerate
                )

            # Ensure stereo (model expects 2 channels)
            if waveform.shape[0] == 1:
                waveform = waveform.repeat(2, 1)
            elif waveform.shape[0] > 2:
                waveform = waveform[:2]

            # Normalize
            ref = waveform.mean(0)
            waveform = (waveform - ref.mean()) / ref.std()

            # Apply model — returns (batch, sources, channels, time)
            logger.info("Running Demucs separation...")
            sources = apply_model(model, waveform.unsqueeze(0), device="cpu")

            # Extract vocals (index 3: ['drums', 'bass', 'other', 'vocals'])
            vocals = sources[0, _VOCALS_INDEX]  # shape: (channels, time)

            # Save vocals
            torchaudio.save(str(vocals_path), vocals.cpu(), model.samplerate)
            duration = vocals.shape[1] / model.samplerate
            logger.info("Vocals saved to %s (%.1fs)", vocals_path, duration)

            return vocals_path

        except FileNotFoundError:
            raise
        except RuntimeError as e:
            if "out of memory" in str(e).lower() or "oom" in str(e).lower():
                raise RuntimeError(
                    f"Out of memory during vocal separation. "
                    f"Try a shorter audio file: {e}"
                ) from e
            raise RuntimeError(f"Vocal separation failed: {e}") from e
        except Exception as e:
            raise RuntimeError(f"Vocal separation failed: {e}") from e
        finally:
            # Memory cleanup
            del sources
            if model is not None:
                self._model = None
                del model
            gc.collect()
