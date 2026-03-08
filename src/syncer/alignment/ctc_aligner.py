"""CTC forced alignment module using torchaudio MMS_FA bundle."""

import logging
from dataclasses import dataclass
from pathlib import Path

import torch
import torchaudio

from syncer.alignment.text_normalize import normalize_for_alignment

logger = logging.getLogger(__name__)

# MMS_FA frame rate: 20.4ms per frame (16000Hz / 320 samples per frame)
_SAMPLES_PER_FRAME = 320
_TARGET_SAMPLE_RATE = 16000


@dataclass
class AlignedWord:
    """A single word with timing and confidence from CTC forced alignment."""

    word: str
    start: float  # seconds
    end: float  # seconds
    score: float = 0.0


@dataclass
class AlignmentResult:
    """Result of CTC forced alignment."""

    words: list[AlignedWord]
    detected_language: str | None


class CTCAligner:
    """Aligns lyrics text to audio using CTC forced alignment with torchaudio MMS_FA.

    Uses lazy loading — model is not downloaded until first align() call.
    """

    def __init__(self, device: str = "cpu") -> None:
        self.device = device
        self._model = None
        self._tokenizer = None
        self._aligner = None

    def _load_model(self):
        """Lazy-load the MMS_FA bundle components."""
        if self._model is None:
            logger.info("Loading MMS_FA model (this may take a moment on first run)...")
            bundle = torchaudio.pipelines.MMS_FA
            self._model = bundle.get_model().to(self.device)
            self._tokenizer = bundle.get_tokenizer()
            self._aligner = bundle.get_aligner()
            logger.info("MMS_FA model loaded")
        return self._model, self._tokenizer, self._aligner

    def align(
        self,
        audio_path: Path,
        lyrics_lines: list[str],
        language: str | None = None,
    ) -> AlignmentResult:
        """Align lyrics text to audio using CTC forced alignment.

        Args:
            audio_path: Path to audio file (any sample rate, any channels).
            lyrics_lines: List of lyrics lines (raw text, will be normalized internally).
            language: Optional ISO 639-1 language code (stored in result, not used
                      for alignment model).

        Returns:
            AlignmentResult with word-level timestamps and detected_language.
        """
        # Step 1: Normalize all lyrics into flat word list
        all_words: list[str] = []
        for line in lyrics_lines:
            words = normalize_for_alignment(line)
            all_words.extend(words)

        if not all_words:
            return AlignmentResult(words=[], detected_language=language)

        # Step 2: Load audio, resample to mono 16kHz
        waveform, sample_rate = torchaudio.load(audio_path)

        # Convert to mono
        if waveform.shape[0] > 1:
            waveform = waveform.mean(dim=0, keepdim=True)

        # Resample if needed
        if sample_rate != _TARGET_SAMPLE_RATE:
            resampler = torchaudio.transforms.Resample(
                orig_freq=sample_rate,
                new_freq=_TARGET_SAMPLE_RATE,
            )
            waveform = resampler(waveform)

        waveform = waveform.to(self.device)

        # Step 3: Load model and tokenize words
        model, tokenizer, aligner = self._load_model()

        try:
            tokens = tokenizer(all_words)
        except KeyError as e:
            logger.warning(
                "Tokenization failed for word (bad character %s), skipping", e
            )
            return AlignmentResult(words=[], detected_language=language)

        # Step 4: Get emission matrix from model
        with torch.inference_mode():
            emission, _ = model(waveform)

        # Step 5: Run forced alignment
        # aligner expects (emission_tensor, token_list) where token_list is list[list[int]]
        word_spans = aligner(emission[0], tokens)

        # Step 6: Convert frame indices to seconds
        aligned_words: list[AlignedWord] = []
        for i, (word_text, spans) in enumerate(zip(all_words, word_spans)):
            if not spans:
                continue
            start_frame = spans[0].start
            end_frame = spans[-1].end
            score = sum(s.score for s in spans) / len(spans)

            start_sec = start_frame * _SAMPLES_PER_FRAME / _TARGET_SAMPLE_RATE
            end_sec = end_frame * _SAMPLES_PER_FRAME / _TARGET_SAMPLE_RATE

            aligned_words.append(
                AlignedWord(
                    word=word_text,
                    start=start_sec,
                    end=end_sec,
                    score=score,
                )
            )

        if len(word_spans) != len(all_words):
            logger.warning(
                "Word span count mismatch: got %d spans for %d words",
                len(word_spans),
                len(all_words),
            )

        return AlignmentResult(words=aligned_words, detected_language=language)
