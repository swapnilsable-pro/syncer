# Learnings — Task 1: ML Smoke Test + Project Scaffolding

## Device Configuration
- **MPS is available** on this macOS machine (Apple Silicon)
- Device detected: `mps` — but WhisperX alignment uses `cpu` (wav2vec2 alignment model)
- `compute_type="float32"` is mandatory for non-CUDA. Confirmed working.

## Demucs
- **Demucs 4.0.1** does NOT have `demucs.api.Separator` class
- Must use lower-level API: `from demucs.pretrained import get_model` + `from demucs.apply import apply_model`
- `apply_model(model, waveform.unsqueeze(0), device="cpu")` returns shape `(batch, sources, channels, time)`
- Sources order: `['drums', 'bass', 'other', 'vocals']` — vocals at index 3
- Model samplerate: 44100 Hz — resample input if needed
- Input must be normalized: `(waveform - ref.mean()) / ref.std()`

## WhisperX
- Installed from GitHub: `git+https://github.com/m-bain/whisperX.git` (commit 064f737)
- WhisperX pinned torch to 2.8.0 (down from pyproject's 2.10.0) — this is fine
- `whisperx.load_model("base", "cpu", compute_type="float32")` works
- Auto-detects language (detected "en" with 0.60 confidence from Rick Astley)
- Alignment model (`wav2vec2_fairseq_base_ls960_asr_ls960.pth`) downloaded from pytorch.org (360MB)

## Memory
- Both models coexist fine with explicit `gc.collect()` between steps
- No OOM observed with `base` model on macOS
- Full pipeline (download + demucs + whisperx transcribe + align) completes in ~55s

## Dependency Issues Encountered
1. **Python 3.14 too new**: `lameenc` (demucs dep) has no wheel for cp314. Solution: pin to Python 3.12
2. **torchaudio backend missing**: torchaudio 2.8.0 couldn't find a decoder backend. Solution: `pip install soundfile`
3. **SSL certificate error**: macOS Python 3.12 missing root certs. Solution: run `/Applications/Python 3.12/Install Certificates.command`
4. **torchcodec warning**: pyannote.audio warns about torchcodec incompatibility with torch 2.8.0 — harmless, doesn't affect functionality

## Extra Dependencies Needed (not in pyproject.toml)
- `soundfile` — required for torchaudio WAV loading backend
- `whisperx` — installed separately from GitHub (not PyPI)

## Test Results
- `test_torch_imports` ✅
- `test_demucs_loads` ✅  
- `test_whisperx_loads` ✅
- `test_full_pipeline` ✅ — 20 words with timestamps from 30s of "Never Gonna Give You Up"
