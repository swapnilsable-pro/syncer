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


@dataclass
class AlignmentResult:
    """Result of transcription + alignment, including detected language."""

    words: list[AlignedWord]
    detected_language: str


def _validate_language(language: str) -> None:
    """Validate language is a 2-letter ISO 639-1 code."""
    if not (len(language) == 2 and language.isalpha() and language.islower()):
        raise ValueError(
            f"Invalid language code {language!r}. Use 2-letter ISO 639-1 codes like 'hi', 'en', 'ur'."
        )

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

    def align(self, audio_path: Path, language: str | None = None) -> AlignmentResult:
        """Transcribe and align audio to produce word-level timestamps.

        Args:
            audio_path: Path to audio file (WAV recommended, 16kHz mono).
            language: Optional ISO 639-1 language code (e.g. 'hi', 'en').
                      If None, WhisperX auto-detects the language.

        Returns:
            AlignmentResult with words and detected language.

        Raises:
            ValueError: If language code is invalid.
        """
        if language is not None:
            _validate_language(language)

        audio_path = Path(audio_path)
        logger.info("Transcribing: %s", audio_path)

        audio = whisperx.load_audio(str(audio_path))
        result = self.model.transcribe(audio, batch_size=8, language=language)

        detected_lang = result.get("language", language or "unknown")

        segments = result.get("segments", [])
        if not segments:
            logger.info("No segments found (silent/empty audio)")
            return AlignmentResult(words=[], detected_language=detected_lang)

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
        return AlignmentResult(words=words, detected_language=detected_lang)
