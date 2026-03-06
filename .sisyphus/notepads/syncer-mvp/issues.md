# Issues — Task 1: ML Smoke Test + Project Scaffolding

## Resolved
1. **Python version**: System default is 3.14.2 which is too new for `lameenc`. Fixed by using `uv venv --python 3.12.8`
2. **Demucs API mismatch**: Plan specified `demucs.api.Separator` but Demucs 4.0.1 doesn't have it. Used `demucs.pretrained.get_model` + `demucs.apply.apply_model` instead.
3. **torchaudio no backend**: Needed `soundfile` package for WAV file I/O
4. **SSL certs on macOS**: Python 3.12 framework install missing root CA certs. Ran Install Certificates.command

## Known Warnings (Non-blocking)
- torchcodec incompatible with torch 2.8.0 on this machine (pyannote.audio warning). Does not affect WhisperX functionality since we use torchaudio+soundfile for audio I/O.
