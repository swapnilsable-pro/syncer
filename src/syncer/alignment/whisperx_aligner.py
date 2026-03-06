"""WhisperX word-level alignment module."""

import gc
import logging
from dataclasses import dataclass
from pathlib import Path

import torch
import whisperx

logger = logging.getLogger(__name__)


@dataclass
class AlignedWord:
    """A single word with timing and confidence from WhisperX alignment."""

    word: str
    start: float
    end: float
    score: float = 0.0


class WordAligner:
    """Transcribes audio and produces word-level timestamps using WhisperX.

    Uses WhisperX's two-stage pipeline:
    1. Transcribe with faster-whisper backend
    2. Align with wav2vec2 for word-level timestamps
    """

    def __init__(
        self,
        model_name: str = "base",
        device: str = "cpu",
        compute_type: str = "float32",
    ) -> None:
        self.device = device
        logger.info(
            "Loading WhisperX model: %s (device=%s, compute=%s)",
            model_name,
            device,
            compute_type,
        )
        self.model = whisperx.load_model(model_name, device, compute_type=compute_type)
        # Load alignment model once
        self.align_model, self.align_metadata = whisperx.load_align_model(
            language_code="en", device=device
        )

    def align(self, audio_path: Path) -> list[AlignedWord]:
        """Transcribe and align audio to produce word-level timestamps.

        Args:
            audio_path: Path to audio file (WAV recommended, 16kHz mono).

        Returns:
            List of AlignedWord with word text, start/end times, and confidence score.
            Returns empty list for silent/empty audio.
        """
        audio_path = Path(audio_path)
        logger.info("Transcribing: %s", audio_path)

        audio = whisperx.load_audio(str(audio_path))
        result = self.model.transcribe(audio, batch_size=8)

        segments = result.get("segments", [])
        if not segments:
            logger.info("No segments found (silent/empty audio)")
            return []

        # Align for word-level timestamps
        logger.info("Aligning %d segments for word-level timestamps", len(segments))
        result = whisperx.align(
            segments, self.align_model, self.align_metadata, audio, self.device
        )

        # Memory cleanup
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        # Extract words
        words = []
        for segment in result.get("segments", []):
            for w in segment.get("words", []):
                words.append(
                    AlignedWord(
                        word=w["word"],
                        start=w.get("start", 0.0),
                        end=w.get("end", 0.0),
                        score=w.get("score", 0.0),  # score may be missing
                    )
                )

        logger.info("Extracted %d words with timestamps", len(words))
        return words
