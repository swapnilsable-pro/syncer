# Decisions — Task 1: ML Smoke Test + Project Scaffolding

## D1: Python 3.12 over 3.14
- **Why**: lameenc (demucs dependency) lacks cp314 wheels
- **Impact**: None — 3.12 is well-supported by all ML libraries

## D2: Demucs low-level API over Separator class
- **Why**: `demucs.api.Separator` doesn't exist in demucs 4.0.1
- **API used**: `demucs.pretrained.get_model("htdemucs")` + `demucs.apply.apply_model(model, audio, device)`
- **Impact**: Future Task 4 (demucs_separator.py) must use this API, not the Separator class

## D3: CPU for WhisperX alignment
- **Why**: wav2vec2 alignment model runs on CPU; MPS available for transcription but CPU is stable
- **Impact**: Alignment step is fast enough on CPU (~2s for 30s audio)

## D4: soundfile as torchaudio backend
- **Why**: torchaudio 2.8.0 needs an external backend; torchcodec incompatible with this torch version
- **Impact**: Must keep soundfile in dependencies
