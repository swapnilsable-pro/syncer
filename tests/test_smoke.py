"""ML smoke tests — verify Demucs and WhisperX load and produce output."""

import pytest


def test_torch_imports():
    import torch

    assert torch.__version__
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    assert device in ("mps", "cpu")


def test_demucs_loads():
    from demucs.pretrained import get_model

    model = get_model("htdemucs")
    assert model is not None
    assert "vocals" in model.sources


def test_whisperx_loads():
    import whisperx

    device = "cpu"
    model = whisperx.load_model("base", device, compute_type="float32")
    assert model is not None


@pytest.mark.slow
def test_full_pipeline():
    """Full smoke test: download, separate, align."""
    import gc
    import json
    import subprocess
    import tempfile
    from pathlib import Path

    import torch
    import torchaudio
    import whisperx
    from demucs.apply import apply_model
    from demucs.pretrained import get_model

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    evidence = {
        "device": device,
        "demucs_model": "htdemucs",
        "demucs_api": "pretrained.get_model + apply.apply_model",
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        # Download short clip (first 30 seconds)
        audio_path = Path(tmpdir) / "test.wav"
        result = subprocess.run(
            [
                "yt-dlp",
                "-x",
                "--audio-format",
                "wav",
                "-o",
                str(audio_path),
                "--download-sections",
                "*0:00-0:30",
                "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
            ],
            capture_output=True,
            timeout=120,
        )

        # Find the actual output file (yt-dlp may add extensions)
        wav_files = list(Path(tmpdir).glob("*.wav"))
        assert len(wav_files) > 0, (
            f"No WAV file downloaded. stderr: {result.stderr.decode()}"
        )
        audio_path = wav_files[0]

        # Load audio
        waveform, sr = torchaudio.load(str(audio_path))

        # Demucs separation
        model = get_model("htdemucs")
        model_sr = model.samplerate

        # Resample if needed
        if sr != model_sr:
            waveform = torchaudio.functional.resample(waveform, sr, model_sr)

        # Normalize
        ref = waveform.mean(0)
        waveform_norm = (waveform - ref.mean()) / ref.std()

        # apply_model expects (batch, channels, time)
        sources = apply_model(model, waveform_norm.unsqueeze(0), device="cpu")
        vocals_idx = model.sources.index("vocals")
        vocals = sources[0, vocals_idx]

        assert vocals.shape[-1] > 0, "Vocals tensor is empty"
        evidence["vocals_shape"] = list(vocals.shape)

        # Save vocals to WAV for WhisperX
        vocals_path = Path(tmpdir) / "vocals.wav"
        # Denormalize
        vocals_out = vocals * ref.std() + ref.mean()
        torchaudio.save(str(vocals_path), vocals_out.cpu(), model_sr)

        # Free Demucs memory
        del model, sources, waveform, waveform_norm
        gc.collect()

        # WhisperX transcribe + align
        wx_model = whisperx.load_model("base", "cpu", compute_type="float32")
        audio = whisperx.load_audio(str(vocals_path))
        result = wx_model.transcribe(audio, batch_size=8)
        assert "segments" in result

        # Free transcription model before loading alignment model
        del wx_model
        gc.collect()

        model_a, metadata = whisperx.load_align_model(language_code="en", device="cpu")
        result = whisperx.align(result["segments"], model_a, metadata, audio, "cpu")

        # Verify word-level timestamps
        all_words = []
        for seg in result["segments"]:
            all_words.extend(seg.get("words", []))

        assert len(all_words) > 0, "No word timestamps produced"

        # Each word should have start, end
        first_word = all_words[0]
        assert "start" in first_word
        assert "end" in first_word

        evidence["word_timestamps"] = all_words[:10]  # First 10 words
        evidence["total_words"] = len(all_words)

        # Save evidence
        evidence_dir = Path(__file__).parent.parent / ".sisyphus" / "evidence"
        evidence_dir.mkdir(parents=True, exist_ok=True)
        with open(evidence_dir / "task-1-smoke-pipeline.json", "w") as f:
            json.dump(evidence, f, indent=2, default=str)

        # Free alignment model
        del model_a, metadata
        gc.collect()
