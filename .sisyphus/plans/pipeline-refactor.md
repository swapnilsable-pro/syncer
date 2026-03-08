# Pipeline Refactor: WhisperX → CTC Forced Alignment

## TL;DR

> **Quick Summary**: Replace WhisperX (ASR transcription + snap alignment) with torchaudio MMS_FA CTC forced alignment. Known lyrics from LRCLIB are aligned directly to vocal audio — no transcription step, no snapping. More accurate, fewer moving parts, zero new heavy dependencies.
>
> **Deliverables**:
> - New `ctc_aligner.py` module using torchaudio MMS_FA
> - Refactored `pipeline.py` with mandatory LRCLIB and CTC alignment
> - Removed WhisperX dependency, snap.py, and all whisperx_only paths
> - Full TDD test suite for new aligner
> - Cache cleared and ready for reprocessing
>
> **Estimated Effort**: Medium (8-12 tasks across 4 waves)
> **Parallel Execution**: YES - 4 waves
> **Critical Path**: Task 1 → Task 2 → Task 3 → Task 5 → Task 7 → Task 9 → Final

---

## Context

### Original Request
User wants to stop relying on WhisperX for word detection. When lyrics are available from LRCLIB, the pipeline should use CTC forced alignment to directly map lyrics text to audio — not transcribe the audio and then match. LRCLIB becomes mandatory (no lyrics = graceful skip). Use the latest tools possible.

### Interview Summary
**Key Discussions**:
- WhisperX does redundant work: transcribes audio into text, then snap.py matches that text to known lyrics. Two sources of error.
- CTC forced alignment takes known text + audio directly → word timestamps. One source of error.
- torchaudio MMS_FA is already installed (torch 2.10, torchaudio 2.10), supports 1130+ languages.
- `forced_align()` was saved from deprecation in torchaudio 2.10.
- snap.py becomes unnecessary — CTC directly aligns text to audio.
- uroman needed for Hindi/Urdu/non-Latin romanization.

**Research Findings**:
- MMS_FA model: 28 romanized character vocab (a-z, ', *), 16kHz mono input, ~49fps frame rate (20.4ms/frame)
- Tokenizer CRASHES on uppercase, digits, punctuation (except ' and -). Text normalization is critical.
- CPU viable for single songs (~30-60s on modern CPU)
- MMS_FA trained on speech not singing — Demucs vocal isolation mitigates domain gap
- Qwen3-ForcedAligner (Jan 2026) is 3-4x more accurate but no Hindi/Urdu — future upgrade path

### Metis Review
**Identified Gaps** (all addressed in plan):
- Tokenizer crash risk on real lyrics — addressed via normalize_text() as FIRST task
- compute_confidence() orphaned by snap.py deletion — relocate before deleting
- Demucs outputs stereo 44.1kHz, MMS_FA needs mono 16kHz — aligner must resample
- detected_language field: MMS_FA doesn't auto-detect — accept None
- Numbers in lyrics: tokenizer crashes on digits — strip/skip
- timing_source values need updating across codebase
- uroman installation needs verification
- whisperx is NOT in pyproject.toml (installed manually)
- python-Levenshtein can be removed with snap.py

---

## Work Objectives

### Core Objective
Replace WhisperX-based alignment with CTC forced alignment using torchaudio MMS_FA, making LRCLIB lyrics mandatory, and eliminating the ASR transcription step entirely.

### Concrete Deliverables
- `src/syncer/alignment/ctc_aligner.py` — New CTC forced alignment module
- `src/syncer/pipeline.py` — Refactored pipeline with mandatory LRCLIB + CTC alignment
- `src/syncer/config.py` — Cleaned up (whisperx_* → ctc_* settings)
- `tests/test_ctc_aligner.py` — Full TDD test suite for new aligner
- Updated `tests/test_pipeline.py`, `tests/test_e2e.py`, `tests/test_models.py`
- Deleted: `whisperx_aligner.py`, `snap.py`, `test_whisperx_aligner.py`, `test_snap.py`
- Cleared cache DB

### Definition of Done
- [ ] `grep -r "whisperx" src/syncer/ --include="*.py"` returns zero matches
- [ ] `python -m pytest tests/ -m "not slow and not integration"` passes all tests
- [ ] `python -c "from syncer.alignment.ctc_aligner import CTCAligner"` imports successfully
- [ ] `python -m syncer "Rick Astley - Never Gonna Give You Up"` produces SyncResult with word timestamps via CTC

### Must Have
- CTC forced alignment using torchaudio MMS_FA for all word-level timestamps
- LRCLIB mandatory — no lyrics = graceful skip with `timing_source="no_lyrics"`, `lines=[]`, `confidence=0.0`
- Text normalization handling: uppercase, punctuation, numbers, Unicode
- uroman integration for non-Latin scripts (Hindi, Urdu)
- Audio resampling: stereo 44.1kHz → mono 16kHz before alignment
- TDD: tests written before implementation
- Cache cleared (old whisperx_only entries become stale)

### Must NOT Have (Guardrails)
- ❌ No fallback to WhisperX or any ASR transcription
- ❌ No language detection library — accept None for detected_language
- ❌ No changes to FastAPI endpoints, response schema, or Pydantic models structure
- ❌ No changes to Demucs, YouTube client, Spotify client, or LRCLIB client
- ❌ No frontend/static file changes
- ❌ No batch/parallel processing additions
- ❌ No "smart" punctuation handling (emoji detection, etc.) — simple regex strip
- ❌ No audio format support expansion
- ❌ No new CLI commands beyond what's needed
- ❌ No keeping snap.py "as fallback" — clean removal, no dead code
- ❌ No over-abstraction or unnecessary factory patterns

---

## Verification Strategy (MANDATORY)

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES (pytest, pytest-asyncio)
- **Automated tests**: TDD (tests first)
- **Framework**: pytest
- **Each task follows**: RED (failing test) → GREEN (minimal impl) → REFACTOR

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Module tests**: Use Bash (pytest) — Run test suite, assert pass/fail
- **Integration**: Use Bash (python -m syncer) — Run CLI, verify JSON output
- **API**: Use Bash (curl) — Send requests, assert responses

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Foundation — start immediately, MAX PARALLEL):
├── Task 1: Text normalization module + exhaustive tests [deep]
├── Task 2: Relocate compute_confidence + clean up alignment/__init__.py [quick]
├── Task 3: Config cleanup (whisperx_* → ctc_*) + add uroman dep [quick]
└── Task 4: Verify uroman installation + write romanization helper [quick]

Wave 2 (Core — after Wave 1):
├── Task 5: CTCAligner module (TDD — tests then implementation) [deep]
├── Task 6: Real-audio smoke test — validate MMS_FA on singing voice [deep]
└── Task 7: Pipeline refactor — mandatory LRCLIB + CTC integration [deep]

Wave 3 (Cleanup — after Wave 2):
├── Task 8: Delete old modules + remove dead deps [quick]
├── Task 9: Update all remaining tests [unspecified-high]
└── Task 10: Cache clear + migration [quick]

Wave FINAL (Verification — after ALL tasks):
├── Task F1: Plan compliance audit [oracle]
├── Task F2: Code quality review [unspecified-high]
├── Task F3: Real QA — run CLI on 3 reference songs [unspecified-high]
└── Task F4: Scope fidelity check [deep]

Critical Path: Task 1 → Task 5 → Task 7 → Task 9 → F1-F4
Parallel Speedup: ~60% faster than sequential
Max Concurrent: 4 (Wave 1)
```

### Dependency Matrix

| Task | Depends On | Blocks |
|------|-----------|--------|
| 1 | — | 5, 7 |
| 2 | — | 7, 8 |
| 3 | — | 5, 7 |
| 4 | — | 5 |
| 5 | 1, 3, 4 | 6, 7 |
| 6 | 5 | 7 |
| 7 | 2, 5, 6 | 8, 9, 10 |
| 8 | 7 | 9 |
| 9 | 7, 8 | F1-F4 |
| 10 | 7 | F1-F4 |

### Agent Dispatch Summary

- **Wave 1**: 4 tasks — T1 → `deep`, T2 → `quick`, T3 → `quick`, T4 → `quick`
- **Wave 2**: 3 tasks — T5 → `deep`, T6 → `deep`, T7 → `deep`
- **Wave 3**: 3 tasks — T8 → `quick`, T9 → `unspecified-high`, T10 → `quick`
- **FINAL**: 4 tasks — F1 → `oracle`, F2 → `unspecified-high`, F3 → `unspecified-high`, F4 → `deep`

---

## TODOs


- [x] 1. Text Normalization Module + Exhaustive Tests (TDD)

  **What to do**:
  - Create `src/syncer/alignment/text_normalize.py` with `normalize_for_alignment(text: str) -> list[str]`
  - Function takes raw lyrics text (may contain uppercase, punctuation, numbers, Unicode) and returns list of cleaned words safe for MMS_FA tokenizer
  - Rules: lowercase everything, strip all punctuation except `'` and `-`, remove digits (skip words that are only digits), collapse whitespace
  - For non-Latin scripts: check if uroman is available, romanize if so
  - Write EXHAUSTIVE tests FIRST in `tests/test_text_normalize.py`:
    - `"Hello World!"` → `["hello", "world"]`
    - `"Don't stop"` → `["don't", "stop"]`
    - `"99 Luftballons"` → `["luftballons"]` (digit-only word stripped)
    - `"Rock & Roll!!!"` → `["rock", "roll"]`
    - `""` → `[]`
    - `"  spaces  everywhere  "` → `["spaces", "everywhere"]`
    - `"24K Magic"` → `["k", "magic"]` (digits stripped from mixed word)
    - `"rock-n-roll"` → `["rock-n-roll"]` (hyphen preserved)
    - `"Héllo café"` → `["hello", "cafe"]` or romanized equivalent
    - Lines with only punctuation → `[]`
    - Very long lyrics text (100+ words) → correctly processed

  **Must NOT do**:
  - No emoji detection or "smart" handling — simple regex
  - No language detection
  - No external NLP libraries besides uroman

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: TDD task with exhaustive edge cases, needs careful implementation
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 2, 3, 4)
  - **Blocks**: Tasks 5, 7
  - **Blocked By**: None

  **References**:
  - `src/syncer/alignment/whisperx_aligner.py:32-37` — Current `_validate_language()` pattern to follow for validation style
  - `src/syncer/alignment/demucs_separator.py` — Module structure pattern (dataclass, docstrings, type hints)
  - MMS_FA tokenizer vocab: `('-', 'a', 'i', 'e', 'n', 'o', 'u', 't', 's', 'r', 'm', 'k', 'l', 'd', 'g', 'h', 'y', 'b', 'p', 'w', 'c', 'v', 'j', 'z', 'f', "'", 'q', 'x', '*')` — ONLY these characters are safe
  - Metis finding: `tokenizer(['Hello'])` → `KeyError: 'H'`, `tokenizer(['99'])` → `KeyError: '9'`, `tokenizer(['hello!'])` → `KeyError: '!'`

  **Acceptance Criteria**:
  - [ ] `python -m pytest tests/test_text_normalize.py -v` → ALL PASS
  - [ ] `python -c "from syncer.alignment.text_normalize import normalize_for_alignment; print(normalize_for_alignment('Hello World!'))"` → `['hello', 'world']`

  **QA Scenarios:**
  ```
  Scenario: Happy path — standard English lyrics
    Tool: Bash (pytest)
    Steps:
      1. Run: python -m pytest tests/test_text_normalize.py -v -k "test_basic"
      2. Assert exit code 0, all tests pass
    Expected Result: All basic normalization tests pass
    Evidence: .sisyphus/evidence/task-1-normalize-basic.txt

  Scenario: Edge cases — punctuation, numbers, empty input
    Tool: Bash (pytest)
    Steps:
      1. Run: python -m pytest tests/test_text_normalize.py -v -k "test_edge"
      2. Assert exit code 0
    Expected Result: All edge case tests pass
    Evidence: .sisyphus/evidence/task-1-normalize-edge.txt
  ```

  **Commit**: YES (group with Wave 1)
  - Message: `feat(alignment): add text normalization for CTC forced alignment`
  - Files: `src/syncer/alignment/text_normalize.py`, `tests/test_text_normalize.py`

- [x] 2. Relocate compute_confidence + Clean Up alignment/__init__.py

  **What to do**:
  - Move `compute_confidence()` function from `src/syncer/alignment/snap.py` to `src/syncer/alignment/__init__.py`
  - This function is imported by `pipeline.py:line 12` as `from syncer.alignment.snap import compute_confidence`
  - Update the import in `pipeline.py` to: `from syncer.alignment import compute_confidence`
  - Verify `compute_confidence` works identically (same signature, same output)
  - Do NOT delete snap.py yet — just move the function
  - Write a simple test verifying the import path works

  **Must NOT do**:
  - Do NOT modify compute_confidence logic
  - Do NOT delete snap.py (that's Task 8)
  - Do NOT touch any other pipeline imports

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Small refactor, move one function between files
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 3, 4)
  - **Blocks**: Tasks 7, 8
  - **Blocked By**: None

  **References**:
  - `src/syncer/alignment/snap.py:334-352` — `compute_confidence()` function to move
  - `src/syncer/pipeline.py:12` — Current import: `from syncer.alignment.snap import snap_words_to_lyrics, compute_confidence`
  - `src/syncer/alignment/__init__.py` — Currently empty, will become the new home

  **Acceptance Criteria**:
  - [ ] `python -c "from syncer.alignment import compute_confidence; print('OK')"` → prints OK
  - [ ] `python -m pytest tests/ -m "not slow and not integration" -q` → no new failures

  **QA Scenarios:**
  ```
  Scenario: Import path works
    Tool: Bash
    Steps:
      1. Run: python -c "from syncer.alignment import compute_confidence; print(compute_confidence([]))"
      2. Assert output is 0.0
    Expected Result: Function importable from new location, returns 0.0 for empty input
    Evidence: .sisyphus/evidence/task-2-import-check.txt
  ```

  **Commit**: YES (group with Wave 1)
  - Message: `refactor(alignment): relocate compute_confidence to alignment/__init__`
  - Files: `src/syncer/alignment/__init__.py`, `src/syncer/pipeline.py`

- [x] 3. Config Cleanup + Add uroman Dependency

  **What to do**:
  - In `src/syncer/config.py`: Remove `whisperx_model`, `whisperx_device`, `whisperx_compute_type` settings
  - Add new settings: `ctc_device: str = "cpu"` and `ctc_model: str = "MMS_FA"` (future-proofing for Qwen3)
  - In `pyproject.toml`: Remove `python-Levenshtein` from dependencies, add `uroman`
  - Run existing tests to verify nothing breaks from config changes

  **Must NOT do**:
  - Do NOT change any non-config settings (spotify, demucs, cache, etc.)
  - Do NOT add GPU detection logic — just accept device string
  - Do NOT rename environment variable prefix (SYNCER_)

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Small config edits across 2 files, no complex logic
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2, 4)
  - **Blocks**: Tasks 5, 7
  - **Blocked By**: None

  **References**:

  **Pattern References**:
  - `src/syncer/config.py:5-17` — Full Settings class. Lines 10-12 are the whisperx_* fields to remove. Line 13 (`demucs_model`) shows naming convention to follow for new ctc_* fields.

  **API/Type References**:
  - `pyproject.toml:5-16` — dependencies list. Line 12 (`python-Levenshtein`) to remove, add `uroman` in its place.

  **Test References**:
  - `tests/test_models.py:155-175` — Tests that construct Settings objects with whisperx_* fields. These will need updating to use ctc_* fields. The executor should check ALL test files for `whisperx_model`, `whisperx_device`, `whisperx_compute_type` references.
  - `tests/test_pipeline.py:46-55` — `_make_settings()` helper constructs Settings with whisperx_* fields.

  **WHY Each Reference Matters**:
  - config.py: Executor needs to see exact field names and types to do clean replacement
  - pyproject.toml: Must not accidentally remove wrong dependency
  - test_models.py + test_pipeline.py: Settings construction will break without updating whisperx_* to ctc_* in tests

  **Acceptance Criteria**:
  - [ ] `python -c "from syncer.config import Settings; s = Settings(); print(s.ctc_device)"` prints `cpu`
  - [ ] `grep -r 'whisperx_model' src/syncer/config.py` returns 0 matches
  - [ ] `grep 'python-Levenshtein' pyproject.toml` returns 0 matches
  - [ ] `grep 'uroman' pyproject.toml` returns 1 match
  - [ ] `python -m pytest tests/test_models.py -v -q` all pass

  **QA Scenarios:**
  ```
  Scenario: Happy path — new config fields work
    Tool: Bash
    Steps:
      1. Run: python -c "from syncer.config import Settings; s = Settings(); print(s.ctc_device, s.ctc_model, s.demucs_model)"
      2. Assert output contains: cpu MMS_FA htdemucs
    Expected Result: New ctc_* settings accessible with correct defaults, demucs unchanged
    Evidence: .sisyphus/evidence/task-3-config-defaults.txt

  Scenario: Failure — old whisperx fields no longer exist
    Tool: Bash
    Steps:
      1. Run: python -c "from syncer.config import Settings; s = Settings(); print(s.whisperx_model)" 2>&1 || true
      2. Assert output contains: AttributeError
    Expected Result: Accessing whisperx_model raises AttributeError
    Evidence: .sisyphus/evidence/task-3-config-no-whisperx.txt
  ```

  **Commit**: YES (group with Wave 1)
  - Message: `refactor(config): replace whisperx settings with ctc, add uroman dep`
  - Files: `src/syncer/config.py`, `pyproject.toml`, `tests/test_models.py`, `tests/test_pipeline.py`

- [x] 4. Verify uroman Installation + Write Romanization Helper

  **What to do**:
  - Write tests FIRST in `tests/test_text_normalize.py` (extend Task 1's test file) for romanization:
    - `romanize("namaste_hindi")` returns romanized ASCII string
    - `romanize("hello")` returns `"hello"` unchanged (already Latin)
    - `romanize("")` returns `""`
    - Non-Latin CJK input returns romanized output
  - Add `romanize(text: str) -> str` function to `src/syncer/alignment/text_normalize.py`
  - Use the `uroman` pip package. Check if `import uroman` works after install.
  - If uroman is a CLI tool not a library: use `subprocess.run(["uroman"], ...)` with proper error handling
  - The function should detect non-Latin script and only romanize when needed (checking if any char is outside ASCII a-z range after lowering)
  - Integrate romanize() into normalize_for_alignment() for non-Latin input: romanize first, then strip/clean

  **Must NOT do**:
  - Do NOT add language detection libraries
  - Do NOT hardcode script-to-language mappings
  - Do NOT make romanization mandatory for Latin text
  - Do NOT fail if uroman is not installed — log warning and return original text cleaned as best-effort

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Small helper function with subprocess call and Latin-detection logic
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 1, 2, 3)
  - **Blocks**: Task 5
  - **Blocked By**: None (but logically extends Task 1's file — can be done in parallel if different test functions)

  **References**:

  **Pattern References**:
  - `src/syncer/alignment/text_normalize.py` (created by Task 1) — Add romanize() here and integrate into normalize_for_alignment()

  **External References**:
  - uroman pip package: `pip install uroman` — Check https://pypi.org/project/uroman/ for API
  - uroman GitHub: https://github.com/isi-nlp/uroman — CLI usage: `echo 'text' | uroman`
  - MMS_FA vocab: only `a-z`, `'`, `*` are accepted — romanization must produce only these characters

  **WHY Each Reference Matters**:
  - text_normalize.py: Must integrate into existing normalize pipeline, not create separate module
  - uroman docs: Need to understand if it's importable as library or CLI-only
  - MMS_FA vocab: romanized output must be filtered to only MMS_FA-safe characters

  **Acceptance Criteria**:
  - [ ] `python -c "from syncer.alignment.text_normalize import romanize; print(romanize('hello'))"` prints `hello`
  - [ ] `python -m pytest tests/test_text_normalize.py -v -k 'roman'` ALL PASS
  - [ ] Romanize function handles missing uroman gracefully (no crash)

  **QA Scenarios:**
  ```
  Scenario: Happy path — Latin text passes through unchanged
    Tool: Bash
    Steps:
      1. Run: python -c "from syncer.alignment.text_normalize import romanize; print(repr(romanize('hello world')))"
      2. Assert output: 'hello world'
    Expected Result: Latin text returned unchanged
    Evidence: .sisyphus/evidence/task-4-romanize-latin.txt

  Scenario: Non-Latin text gets romanized (if uroman installed)
    Tool: Bash
    Steps:
      1. Run: pip install uroman 2>&1 | tail -1
      2. Run: python -c "from syncer.alignment.text_normalize import romanize; result = romanize('namaste_hindi'); print(repr(result)); assert result.isascii()"
      3. Assert: result is ASCII string
    Expected Result: Hindi text romanized to ASCII
    Evidence: .sisyphus/evidence/task-4-romanize-hindi.txt

  Scenario: Graceful degradation — uroman not installed
    Tool: Bash
    Steps:
      1. Mock uroman import to raise ImportError
      2. Call romanize('test') and verify no crash
    Expected Result: Function does not crash without uroman, returns best-effort cleaned text
    Evidence: .sisyphus/evidence/task-4-romanize-fallback.txt
  ```

  **Commit**: YES (group with Wave 1)
  - Message: `feat(alignment): add uroman romanization helper for non-Latin lyrics`
  - Files: `src/syncer/alignment/text_normalize.py`, `tests/test_text_normalize.py`

- [x] 5. CTCAligner Module (TDD — Tests Then Implementation) — THE CORE TASK

  **What to do**:
  - **RED phase**: Write comprehensive tests FIRST in `tests/test_ctc_aligner.py`:
    - Test CTCAligner instantiation (creates model/tokenizer/aligner lazily)
    - Test `align(audio_path, lyrics_lines, language=None)` with mocked torchaudio:
      - Returns AlignmentResult with words list and detected_language
      - Each word has start, end, score fields
      - Words are sequential (word[i].end <= word[i+1].start, approximately)
      - All timestamps are >= 0 and <= audio duration
      - Score values are between 0.0 and 1.0
    - Test audio resampling: stereo 44.1kHz input resampled to mono 16kHz
    - Test text normalization is called on lyrics before tokenization
    - Test empty lyrics list returns empty AlignmentResult
    - Test single-word lyrics
    - Test very long lyrics (100+ lines)
  - **GREEN phase**: Implement `src/syncer/alignment/ctc_aligner.py`:
    - `class CTCAligner` with lazy model loading (like VocalSeparator pattern)
    - `__init__(self, device: str = "cpu")` — stores config, no loading yet
    - `_load_model(self)` — lazy loads MMS_FA bundle (model, tokenizer, aligner)
    - `align(self, audio_path: Path, lyrics_lines: list[str], language: str | None = None) -> AlignmentResult`:
      1. Load audio with torchaudio.load()
      2. Resample to 16kHz mono if needed (torchaudio.transforms.Resample + mean across channels)
      3. Call normalize_for_alignment() on each lyrics line to get clean word list
      4. Tokenize words with bundle tokenizer
      5. Run model forward pass to get emission matrix
      6. Call bundle aligner (forced_align) to get token spans
      7. Convert frame indices to seconds: frame_idx * 320 / 16000
      8. Build AlignedWord list with word text, start, end, score
      9. Return AlignmentResult(words=aligned_words, detected_language=language or None)
  - **REFACTOR phase**: Clean up, add docstrings, ensure type hints
  - Reuse existing `AlignedWord` and `AlignmentResult` dataclasses (move from whisperx_aligner.py to alignment/__init__.py or keep in ctc_aligner.py)

  **Must NOT do**:
  - Do NOT add batch processing or parallel alignment
  - Do NOT add language auto-detection
  - Do NOT add GPU memory management beyond basic .to(device)
  - Do NOT add fallback to WhisperX if CTC fails
  - Do NOT modify the AlignedWord/AlignmentResult dataclass fields
  - Do NOT add audio format conversion (only resample)

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Core module, TDD workflow, complex torchaudio API integration, needs careful handling of frame-to-time conversion and edge cases
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (starts Wave 2)
  - **Parallel Group**: Wave 2 (with Tasks 6, 7 — but 6 and 7 depend on 5)
  - **Blocks**: Tasks 6, 7
  - **Blocked By**: Tasks 1 (text normalization), 3 (config), 4 (romanization)

  **References**:

  **Pattern References**:
  - `src/syncer/alignment/demucs_separator.py:28-44` — VocalSeparator class: follow this EXACT pattern for lazy loading (_model = None, _load_model method). Copy the logging style.
  - `src/syncer/alignment/whisperx_aligner.py:14-30` — AlignedWord and AlignmentResult dataclasses. These exact classes must be reused (move to __init__.py or redefine identically in ctc_aligner.py)
  - `src/syncer/alignment/whisperx_aligner.py:39-121` — WordAligner class. Study the overall structure but DO NOT copy WhisperX-specific logic.

  **API/Type References**:
  - torchaudio MMS_FA API (verified on user's machine):
    ```python
    bundle = torchaudio.pipelines.MMS_FA
    model = bundle.get_model()          # Wav2Vec2FABundle
    tokenizer = bundle.get_tokenizer()  # list[str] -> list[list[int]]
    aligner = bundle.get_aligner()      # (emission, tokens) -> List[List[TokenSpan]]
    # TokenSpan: .token (int), .start (frame), .end (frame), .score (float)
    # Frame to seconds: frame_index * 320 / 16000
    ```
  - `src/syncer/alignment/text_normalize.py` (Task 1) — normalize_for_alignment() function to call before tokenization
  - `src/syncer/config.py` (Task 3) — `ctc_device` setting for device parameter

  **Test References**:
  - `tests/test_smoke.py:14-28` — Pattern for testing ML model loading (lazy, with assertions)

  **WHY Each Reference Matters**:
  - demucs_separator.py: Exact structural template — lazy load, dataclass result, docstring style
  - whisperx_aligner.py: AlignedWord/AlignmentResult contract that pipeline.py and snap.py consume
  - MMS_FA API: The actual torchaudio calls to make — bundle.get_model(), tokenizer(), aligner()
  - text_normalize.py: MUST call this before tokenization or tokenizer will crash on uppercase/punctuation

  **Acceptance Criteria**:
  - [ ] `python -m pytest tests/test_ctc_aligner.py -v` ALL PASS
  - [ ] `python -c "from syncer.alignment.ctc_aligner import CTCAligner; print('OK')"` prints OK
  - [ ] CTCAligner follows lazy-loading pattern (no model loaded on __init__)
  - [ ] Audio resampling works: accepts any sample rate, outputs mono 16kHz internally

  **QA Scenarios:**
  ```
  Scenario: Happy path — module imports and instantiates
    Tool: Bash
    Steps:
      1. Run: python -c "from syncer.alignment.ctc_aligner import CTCAligner; a = CTCAligner(); print(type(a).__name__)"
      2. Assert output: CTCAligner
      3. Assert no model downloaded yet (lazy loading)
    Expected Result: Class importable and instantiable without downloading model
    Evidence: .sisyphus/evidence/task-5-ctc-import.txt

  Scenario: Unit tests pass with mocked torchaudio
    Tool: Bash (pytest)
    Steps:
      1. Run: python -m pytest tests/test_ctc_aligner.py -v --tb=short
      2. Assert exit code 0
      3. Assert all tests pass
    Expected Result: All TDD tests pass
    Evidence: .sisyphus/evidence/task-5-ctc-tests.txt

  Scenario: Failure — empty lyrics returns empty result
    Tool: Bash
    Steps:
      1. Run: python -c "from syncer.alignment.ctc_aligner import CTCAligner; a = CTCAligner(); r = a.align('/dev/null', []); print(len(r.words))"
      2. Assert output: 0
    Expected Result: Empty lyrics produce empty word list, no crash
    Evidence: .sisyphus/evidence/task-5-ctc-empty.txt
  ```

  **Commit**: YES
  - Message: `feat(alignment): add CTC forced aligner using torchaudio MMS_FA`
  - Files: `src/syncer/alignment/ctc_aligner.py`, `tests/test_ctc_aligner.py`, `src/syncer/alignment/__init__.py`
  - Pre-commit: `python -m pytest tests/test_ctc_aligner.py -v`

- [x] 6. Real-Audio Smoke Test — Validate MMS_FA on Singing Voice

  **What to do**:
  - Create `tests/test_ctc_smoke.py` with a `@pytest.mark.slow` integration test
  - Download a short reference song (use "Rick Astley - Never Gonna Give You Up" via existing YouTube client)
  - Run Demucs vocal isolation on it (using existing VocalSeparator)
  - Run CTCAligner.align() on the isolated vocals with known LRCLIB lyrics
  - Assert:
    - Result has words (len > 20)
    - All timestamps are positive and within song duration
    - Words are roughly sequential (start[i] < start[i+1] for most words)
    - Average confidence score > 0.1 (singing voice may be lower than speech)
  - This test validates the REAL pipeline path, not mocked
  - Save the full AlignmentResult JSON to `.sisyphus/evidence/task-6-smoke-result.json`

  **Must NOT do**:
  - Do NOT modify CTCAligner code — this is VALIDATION only
  - Do NOT add this test to the fast test suite (must be @pytest.mark.slow)
  - Do NOT skip if model download is slow — it's cached after first run

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Integration test requiring real ML model inference, audio processing, and careful assertion design
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (needs Task 5 complete)
  - **Parallel Group**: Wave 2 (after Task 5, can overlap with Task 7 if 5 passes)
  - **Blocks**: Task 7 (confirms aligner works on real audio before pipeline integration)
  - **Blocked By**: Task 5 (CTCAligner must exist)

  **References**:

  **Pattern References**:
  - `tests/test_smoke.py:30-148` — Existing smoke test pattern. Follow this structure: download audio, process, assert, save evidence JSON. The test_full_pipeline() function at line 31 is the closest pattern.
  - `tests/test_e2e.py:18-35` — How reference songs are tested (SyncRequest creation, result assertions)

  **API/Type References**:
  - `src/syncer/alignment/ctc_aligner.py` (Task 5) — CTCAligner.align() returns AlignmentResult
  - `src/syncer/alignment/demucs_separator.py:46` — VocalSeparator.separate() returns Path to vocals WAV
  - `src/syncer/clients/youtube.py` — search_youtube() + extract_audio() for getting test audio
  - `src/syncer/clients/lrclib.py` — fetch_lyrics() for getting known lyrics text

  **WHY Each Reference Matters**:
  - test_smoke.py: Exact pattern to follow for slow ML integration tests
  - CTCAligner: The module under test — need its exact API signature
  - Demucs + YouTube + LRCLIB: Real dependencies needed to get vocals + lyrics for the test

  **Acceptance Criteria**:
  - [ ] `python -m pytest tests/test_ctc_smoke.py -v -m slow` PASSES
  - [ ] Evidence file exists: `.sisyphus/evidence/task-6-smoke-result.json`
  - [ ] Evidence JSON has `words` array with 20+ entries
  - [ ] All word timestamps are positive numbers

  **QA Scenarios:**
  ```
  Scenario: Happy path — CTC alignment produces sensible results on real singing
    Tool: Bash
    Steps:
      1. Run: python -m pytest tests/test_ctc_smoke.py -v -m slow --timeout=300
      2. Assert exit code 0
      3. Read .sisyphus/evidence/task-6-smoke-result.json
      4. Assert: words array length > 20
      5. Assert: all start times < end times
      6. Assert: average score > 0.0
    Expected Result: MMS_FA aligner produces valid word timestamps from singing voice
    Failure Indicators: Empty words array, all-zero timestamps, scores all 0.0
    Evidence: .sisyphus/evidence/task-6-smoke-result.json

  Scenario: Failure — graceful error on corrupted audio
    Tool: Bash
    Steps:
      1. Create a zero-byte file as fake audio
      2. Call CTCAligner.align() on it
      3. Assert: raises RuntimeError with descriptive message (not cryptic torchaudio error)
    Expected Result: Clear error message, not unhandled exception
    Evidence: .sisyphus/evidence/task-6-smoke-bad-audio.txt
  ```

  **Commit**: YES
  - Message: `test(alignment): add real-audio smoke test for CTC aligner`
  - Files: `tests/test_ctc_smoke.py`
  - Pre-commit: `python -m pytest tests/test_ctc_smoke.py -v -m slow`

- [x] 7. Pipeline Refactor — Mandatory LRCLIB + CTC Integration

  **What to do**:
  - **This is the biggest refactor task.** Rewrite `src/syncer/pipeline.py` sync() method:
  - **Step 1**: Replace `WordAligner` import with `CTCAligner` import
    - Old: `from syncer.alignment.whisperx_aligner import WordAligner`
    - New: `from syncer.alignment.ctc_aligner import CTCAligner`
  - **Step 2**: Replace `snap_words_to_lyrics` import with `compute_confidence` from new location
    - Old: `from syncer.alignment.snap import snap_words_to_lyrics, compute_confidence`
    - New: `from syncer.alignment import compute_confidence`
  - **Step 3**: Update SyncPipeline.__init__():
    - Old: `self.aligner = WordAligner(settings.whisperx_model, settings.whisperx_device, ...)`
    - New: `self.aligner = CTCAligner(device=settings.ctc_device)`
  - **Step 4**: Make LRCLIB mandatory in sync():
    - If no lyrics found (both synced_lyrics and plain_lyrics are None), return graceful skip:
      ```python
      SyncResult(track=track_info, lines=[], confidence=0.0,
                 timing_source="no_lyrics", cached=False,
                 detected_language=None)
      ```
    - Cache the graceful-skip result too (so repeated queries don't re-download)
    - Remove the `whisperx_only` code path entirely
    - Remove `_lines_from_asr()` method entirely (was for no-lyrics ASR fallback)
  - **Step 5**: Replace Step 6+7 (alignment + snap) with CTC alignment:
    - Old: aligner.align(vocals) -> ASR words -> snap_words_to_lyrics(asr_words, lyrics)
    - New: aligner.align(vocals_path, plain_lyrics_text) -> aligned_words directly
    - Build SyncedLines from aligned words, grouped by lyrics line
    - Set timing_source to `"ctc_aligned"` for all CTC-aligned results
  - **Step 6**: Update timing_source values:
    - `"ctc_aligned"` — lyrics aligned via CTC (replaces "lrclib_enhanced" and "whisperx_only")
    - `"lrclib_synced"` — kept as-is for LRCLIB line-level only (audio extraction failed fallback)
    - `"no_lyrics"` — new value for graceful skip
  - **Step 7**: Update `tests/test_pipeline.py` to match new pipeline:
    - Replace all WordAligner mocks with CTCAligner mocks
    - Remove all snap_words_to_lyrics mocks
    - Add test for graceful skip (no lyrics scenario)
    - Update timing_source assertions to new values
    - Update _make_settings() to use ctc_device instead of whisperx_*

  **Must NOT do**:
  - Do NOT change _resolve_input() method — it's unrelated
  - Do NOT change _parse_video_title() method — it's unrelated
  - Do NOT change cache logic (get_cached, store_result)
  - Do NOT change Demucs, YouTube, Spotify, or LRCLIB client calls
  - Do NOT add retry logic or fallback to WhisperX
  - Do NOT change SyncResult/SyncedLine/SyncedWord model fields

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Largest refactor, touches core pipeline logic, must preserve all non-alignment behavior while completely replacing alignment flow. Requires careful attention to data flow and edge cases.
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 2 (after Tasks 1-6 complete)
  - **Blocks**: Tasks 8, 9, 10
  - **Blocked By**: Tasks 2 (compute_confidence relocated), 5 (CTCAligner exists), 6 (smoke test confirms aligner works)

  **References**:

  **Pattern References**:
  - `src/syncer/pipeline.py:1-228` — THE ENTIRE FILE is being modified. Key sections:
    - Lines 10-12: Imports to replace (whisperx_aligner, snap)
    - Lines 30-38: __init__ to update (WordAligner -> CTCAligner)
    - Lines 67-96: LRCLIB fetch logic (KEEP but add mandatory check)
    - Lines 97-196: Audio + alignment steps (MAJOR REWRITE of steps 5-7)
    - Lines 197-228: Build result + cache (mostly keep, update timing_source)
    - Lines 307-339: _lines_from_asr() — DELETE entirely

  **API/Type References**:
  - `src/syncer/alignment/ctc_aligner.py` (Task 5) — CTCAligner.align(audio_path, lyrics_lines, language) -> AlignmentResult
  - `src/syncer/alignment/__init__.py` (Task 2) — compute_confidence() new import location
  - `src/syncer/models.py` — SyncResult, SyncedLine, SyncedWord models (NOT changing structure)

  **Test References**:
  - `tests/test_pipeline.py:1-751` — ALL 751 lines need review. Key areas:
    - Lines 46-55: _make_settings() uses whisperx_* fields → update to ctc_*
    - Lines 58+: _make_synced_lines() helper — keep as-is
    - Every `@patch` decorator referencing whisperx or snap needs updating
    - Every `timing_source` assertion needs updating to new values

  **WHY Each Reference Matters**:
  - pipeline.py: This IS the file being rewritten — executor must understand full current flow
  - ctc_aligner.py: New module being integrated — need exact API signature
  - test_pipeline.py: 751 lines of tests that will ALL break without careful mock updates

  **Acceptance Criteria**:
  - [ ] `grep -r 'whisperx' src/syncer/pipeline.py` returns 0 matches
  - [ ] `grep -r 'snap_words_to_lyrics' src/syncer/pipeline.py` returns 0 matches
  - [ ] `grep '_lines_from_asr' src/syncer/pipeline.py` returns 0 matches
  - [ ] `grep 'no_lyrics' src/syncer/pipeline.py` returns >= 1 match
  - [ ] `grep 'ctc_aligned' src/syncer/pipeline.py` returns >= 1 match
  - [ ] `python -m pytest tests/test_pipeline.py -v -q` ALL PASS
  - [ ] `python -c "from syncer.pipeline import SyncPipeline; print('OK')"` prints OK

  **QA Scenarios:**
  ```
  Scenario: Happy path — pipeline with lyrics produces CTC-aligned result
    Tool: Bash (pytest)
    Steps:
      1. Run: python -m pytest tests/test_pipeline.py -v -k "test_sync_with_lrclib" --tb=short
      2. Assert exit code 0
      3. Assert timing_source in test output is "ctc_aligned"
    Expected Result: Pipeline integrates CTC aligner, produces word timestamps
    Evidence: .sisyphus/evidence/task-7-pipeline-happy.txt

  Scenario: Graceful skip — no lyrics returns empty result
    Tool: Bash (pytest)
    Steps:
      1. Run: python -m pytest tests/test_pipeline.py -v -k "test_no_lyrics" --tb=short
      2. Assert exit code 0
      3. Assert result has timing_source="no_lyrics", lines=[], confidence=0.0
    Expected Result: Pipeline skips gracefully when LRCLIB has no lyrics
    Evidence: .sisyphus/evidence/task-7-pipeline-no-lyrics.txt

  Scenario: Failure — no WhisperX references remain in pipeline
    Tool: Bash
    Steps:
      1. Run: grep -r 'whisperx\|snap_words\|_lines_from_asr\|whisperx_only' src/syncer/pipeline.py
      2. Assert exit code 1 (no matches)
    Expected Result: Zero references to old alignment system
    Evidence: .sisyphus/evidence/task-7-pipeline-no-whisperx.txt
  ```

  **Commit**: YES
  - Message: `refactor(pipeline): replace WhisperX with CTC forced alignment, mandatory LRCLIB`
  - Files: `src/syncer/pipeline.py`, `tests/test_pipeline.py`
  - Pre-commit: `python -m pytest tests/test_pipeline.py -v`

- [x] 8. Delete Old Modules + Remove Dead Dependencies

  **What to do**:
  - DELETE `src/syncer/alignment/whisperx_aligner.py` entirely
  - DELETE `src/syncer/alignment/snap.py` entirely (compute_confidence already moved in Task 2)
  - DELETE `tests/test_whisperx_aligner.py` entirely
  - DELETE `tests/test_snap.py` entirely
  - Verify NO remaining imports reference these deleted files anywhere:
    - `grep -r 'whisperx_aligner' src/ tests/`
    - `grep -r 'from syncer.alignment.snap' src/ tests/`
  - Clean up any `whisperx` references in `__init__.py` files if they exist
  - Note: whisperx itself is NOT in pyproject.toml (installed manually) so no toml change needed
  - python-Levenshtein was already removed in Task 3

  **Must NOT do**:
  - Do NOT delete demucs_separator.py — it's still used
  - Do NOT delete alignment/__init__.py — it now holds compute_confidence
  - Do NOT uninstall whisperx from the environment (leave it, just don't import it)
  - Do NOT touch any test files except the ones being deleted

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: File deletions + grep verification, no logic changes
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 9, 10 in Wave 3)
  - **Parallel Group**: Wave 3
  - **Blocks**: Task 9 (tests need to not import deleted modules)
  - **Blocked By**: Task 7 (pipeline must be updated before deleting old modules)

  **References**:
  - `src/syncer/alignment/whisperx_aligner.py` — DELETE this file (121 lines)
  - `src/syncer/alignment/snap.py` — DELETE this file (352 lines). Verify compute_confidence was already moved to __init__.py in Task 2.
  - `tests/test_whisperx_aligner.py` — DELETE (305 lines)
  - `tests/test_snap.py` — DELETE (267 lines)

  **Acceptance Criteria**:
  - [ ] `ls src/syncer/alignment/whisperx_aligner.py` → file not found
  - [ ] `ls src/syncer/alignment/snap.py` → file not found
  - [ ] `ls tests/test_whisperx_aligner.py` → file not found
  - [ ] `ls tests/test_snap.py` → file not found
  - [ ] `grep -r 'whisperx_aligner\|from syncer.alignment.snap' src/ tests/` → 0 matches
  - [ ] `python -m pytest tests/ -m 'not slow and not integration' -q` → no import errors

  **QA Scenarios:**
  ```
  Scenario: Happy path — deleted files don't exist
    Tool: Bash
    Steps:
      1. Run: ls src/syncer/alignment/whisperx_aligner.py 2>&1 || echo "DELETED"
      2. Run: ls src/syncer/alignment/snap.py 2>&1 || echo "DELETED"
      3. Assert both output DELETED
    Expected Result: Old alignment modules fully removed
    Evidence: .sisyphus/evidence/task-8-deletions.txt

  Scenario: No dangling imports
    Tool: Bash
    Steps:
      1. Run: grep -r 'whisperx_aligner\|from syncer.alignment.snap' src/ tests/ 2>&1 || echo "CLEAN"
      2. Assert output is CLEAN
      3. Run: python -m pytest tests/ -m 'not slow and not integration' -q --tb=line 2>&1
      4. Assert no ImportError in output
    Expected Result: No remaining references to deleted modules, all imports resolve
    Evidence: .sisyphus/evidence/task-8-no-dangling.txt
  ```

  **Commit**: YES
  - Message: `chore: remove WhisperX aligner, snap.py, and associated tests`
  - Files: (deletions) `src/syncer/alignment/whisperx_aligner.py`, `src/syncer/alignment/snap.py`, `tests/test_whisperx_aligner.py`, `tests/test_snap.py`

- [x] 9. Update All Remaining Tests

  **What to do**:
  - Update `tests/test_smoke.py`:
    - Replace `test_whisperx_loads()` with `test_ctc_aligner_loads()` — verify MMS_FA bundle imports
    - Update `test_full_pipeline()` to use CTC aligner instead of WhisperX
    - Remove all `import whisperx` references
  - Update `tests/test_e2e.py`:
    - Update `timing_source` assertions: remove `"whisperx_aligned"`, `"whisperx_only"`
    - Add expected values: `"ctc_aligned"`, `"lrclib_synced"`, `"no_lyrics"`
    - Add a test for a song unlikely to have LRCLIB lyrics (verify graceful skip)
  - Update `tests/test_models.py`:
    - Update any Settings construction that uses whisperx_* fields to ctc_* fields
    - Add test for `timing_source="no_lyrics"` value
    - Add test for `timing_source="ctc_aligned"` value
  - Update `tests/test_cache.py` (if it references timing_source strings):
    - Update any hardcoded timing_source values
  - Run FULL test suite (non-slow) to verify everything passes

  **Must NOT do**:
  - Do NOT modify test logic for cache, API, YouTube, Spotify, or LRCLIB clients
  - Do NOT add new test files (except maybe conftest updates)
  - Do NOT change test markers or pytest config

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Many test files to update, must understand mock patterns and timing_source semantics, risk of missed references
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: partially (with Task 10)
  - **Parallel Group**: Wave 3
  - **Blocks**: Final Verification (F1-F4)
  - **Blocked By**: Tasks 7 (pipeline refactored), 8 (old modules deleted)

  **References**:

  **Pattern References**:
  - `tests/test_smoke.py:1-148` — Full file. Lines 22-27 (`test_whisperx_loads`) to replace with CTC. Lines 30-148 (`test_full_pipeline`) heavy rewrite.
  - `tests/test_e2e.py:1-147` — Full file. Lines 30-35 have timing_source assertions to update.
  - `tests/test_models.py:1-208` — Full file. Settings construction tests need ctc_* fields.

  **API/Type References**:
  - `src/syncer/config.py` (Task 3) — New Settings fields: ctc_device, ctc_model
  - New timing_source values: `"ctc_aligned"`, `"lrclib_synced"`, `"no_lyrics"`

  **WHY Each Reference Matters**:
  - test_smoke.py: Direct whisperx imports that will crash after deletion
  - test_e2e.py: timing_source assertions will fail with old values
  - test_models.py: Settings construction uses removed field names

  **Acceptance Criteria**:
  - [ ] `grep -r 'whisperx' tests/` → 0 matches
  - [ ] `grep -r 'whisperx_only\|whisperx_aligned' tests/` → 0 matches
  - [ ] `python -m pytest tests/ -m 'not slow and not integration' -v` → ALL PASS
  - [ ] `python -m pytest tests/ -m 'not slow and not integration' -q` → 0 failures

  **QA Scenarios:**
  ```
  Scenario: Happy path — all fast tests pass
    Tool: Bash (pytest)
    Steps:
      1. Run: python -m pytest tests/ -m 'not slow and not integration' -v --tb=short
      2. Assert exit code 0
      3. Assert 0 failures in output
    Expected Result: Full non-slow test suite passes
    Evidence: .sisyphus/evidence/task-9-all-tests.txt

  Scenario: No whisperx references in any test
    Tool: Bash
    Steps:
      1. Run: grep -rn 'whisperx\|WhisperX\|whisper_x' tests/ 2>&1 || echo "CLEAN"
      2. Assert output is CLEAN
    Expected Result: Zero references to WhisperX in test directory
    Evidence: .sisyphus/evidence/task-9-no-whisperx.txt
  ```

  **Commit**: YES
  - Message: `test: update all tests for CTC alignment engine`
  - Files: `tests/test_smoke.py`, `tests/test_e2e.py`, `tests/test_models.py`, `tests/test_cache.py`
  - Pre-commit: `python -m pytest tests/ -m 'not slow and not integration' -q`

- [x] 10. Cache Clear + Migration

  **What to do**:
  - Add a `clear_all()` method to `CacheManager` in `src/syncer/cache.py` if one doesn't exist:
    - `DELETE FROM sync_results` + `DELETE FROM tracks`
    - Log how many entries were cleared
  - Create a one-time migration script `scripts/clear_cache.py`:
    - Import CacheManager and Settings
    - Call clear_all() on the user's default cache DB
    - Print confirmation message with count of cleared entries
  - Alternatively, add a CLI command: `python -m syncer --clear-cache`
  - The goal: user's 9 cached entries (from whisperx_only era) must be cleared so they can reprocess with CTC
  - Run the cache clear as part of this task

  **Must NOT do**:
  - Do NOT delete the SQLite database file — just clear the tables
  - Do NOT change the table schema
  - Do NOT add automatic migration on startup (explicit clear only)
  - Do NOT change CacheManager's get_cached or store_result methods

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Simple DB operation, one new method + one script
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Tasks 8, 9 in Wave 3)
  - **Parallel Group**: Wave 3
  - **Blocks**: Final Verification (F1-F4)
  - **Blocked By**: Task 7 (pipeline must be refactored before clearing cache)

  **References**:

  **Pattern References**:
  - `src/syncer/cache.py:1-157` — Full CacheManager. Lines 10-32 show table schemas. The class uses sqlite3 directly (no ORM). Follow existing method patterns for clear_all().
  - `src/syncer/cache.py:35-38` — generate_track_id() — shows how track IDs are generated (won't change)

  **API/Type References**:
  - `src/syncer/config.py:9` — `db_path` setting points to `~/.syncer/cache.db`
  - `src/syncer/__main__.py` — CLI entry point (if adding --clear-cache flag)

  **WHY Each Reference Matters**:
  - cache.py: Must understand existing table structure and method patterns
  - config.py: Need default db_path to clear the right database

  **Acceptance Criteria**:
  - [ ] `python -c "from syncer.cache import CacheManager; print('clear_all' in dir(CacheManager))"` prints True
  - [ ] Cache clear script/command runs without error
  - [ ] After clearing: `python -c "from syncer.cache import CacheManager; from syncer.config import Settings; c = CacheManager(Settings().db_path); print(len(c.list_tracks()))"` prints 0

  **QA Scenarios:**
  ```
  Scenario: Happy path — cache cleared successfully
    Tool: Bash
    Steps:
      1. Run: python -c "from syncer.cache import CacheManager; from syncer.config import Settings; c = CacheManager(Settings().db_path); print('Before:', len(c.list_tracks()))"
      2. Run the cache clear command/script
      3. Run: python -c "from syncer.cache import CacheManager; from syncer.config import Settings; c = CacheManager(Settings().db_path); print('After:', len(c.list_tracks()))"
      4. Assert: Before count > 0 (or >= 0), After count == 0
    Expected Result: All cached entries cleared
    Evidence: .sisyphus/evidence/task-10-cache-clear.txt

  Scenario: Clear on empty cache doesn't crash
    Tool: Bash
    Steps:
      1. Run cache clear twice in a row
      2. Assert no error on second run
    Expected Result: Idempotent operation
    Evidence: .sisyphus/evidence/task-10-cache-idempotent.txt
  ```

  **Commit**: YES
  - Message: `chore: add cache clear method and clear stale WhisperX-era entries`
  - Files: `src/syncer/cache.py`, `scripts/clear_cache.py` (or `src/syncer/__main__.py`)

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Rejection → fix → re-run.

- [x] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, run command). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Check evidence files exist in .sisyphus/evidence/. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [x] F2. **Code Quality Review** — `unspecified-high`
  Run `python -m pytest tests/ -m "not slow and not integration"` + check all changed files for: `as any`, empty catches, `print()` in prod, commented-out code, unused imports. Check AI slop: excessive comments, over-abstraction, generic names. Verify no WhisperX references remain.
  Output: `Tests [N pass/N fail] | Files [N clean/N issues] | VERDICT`

- [ ] F3. **Real Manual QA** — `unspecified-high`
  Start FastAPI server. Run 3 reference songs through CLI: (1) English song with LRCLIB lyrics, (2) Song with no LRCLIB lyrics (verify graceful skip), (3) Hindi song if uroman works. Verify word timestamps are sensible (start < end, sequential, within song duration). Save outputs to `.sisyphus/evidence/final-qa/`.
  Output: `Songs [N/N pass] | Timestamps valid [YES/NO] | Graceful skip [YES/NO] | VERDICT`

- [x] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff. Verify 1:1 — everything in spec was built, nothing beyond spec was built. Check "Must NOT do" compliance. Detect unaccounted changes. Verify Demucs/LRCLIB/YouTube/Spotify clients were NOT touched.
  Output: `Tasks [N/N compliant] | Unaccounted [CLEAN/N files] | VERDICT`

---

## Commit Strategy

- **Wave 1**: `refactor(alignment): extract compute_confidence, add text normalization` — alignment/__init__.py, config.py, pyproject.toml
- **Wave 2**: `feat(alignment): add CTC forced aligner using torchaudio MMS_FA` — ctc_aligner.py, test_ctc_aligner.py
- **Wave 2**: `refactor(pipeline): replace WhisperX with CTC forced alignment, mandatory LRCLIB` — pipeline.py, test_pipeline.py
- **Wave 3**: `chore: remove WhisperX, snap.py, and dead dependencies` — deletions + test updates
- **Wave 3**: `chore: clear cache for reprocessing with new alignment engine` — cache migration

---

## Success Criteria

### Verification Commands
```bash
# All fast tests pass
python -m pytest tests/ -m "not slow and not integration" -q
# Expected: All pass, 0 failures

# No WhisperX references
grep -r "whisperx" src/syncer/ --include="*.py"
# Expected: 0 matches

# New aligner importable
python -c "from syncer.alignment.ctc_aligner import CTCAligner; print('OK')"
# Expected: prints "OK"

# CLI works end-to-end
python -m syncer "Rick Astley - Never Gonna Give You Up"
# Expected: JSON with lines[], words with timestamps, timing_source="ctc_aligned"
```

### Final Checklist
- [ ] All "Must Have" present
- [ ] All "Must NOT Have" absent
- [ ] All fast tests pass
- [ ] CLI produces valid SyncResult with CTC-aligned word timestamps
- [ ] No lyrics → graceful skip (timing_source="no_lyrics", lines=[])
- [ ] Cache cleared, ready for reprocessing
