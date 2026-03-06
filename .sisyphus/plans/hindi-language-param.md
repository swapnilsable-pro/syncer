# Add Language Parameter for Hindi/Multi-Language Support

## TL;DR

> **Quick Summary**: Thread an optional `language` parameter through the entire pipeline so users can force `language="hi"` for Hindi songs instead of Whisper auto-detecting (and often misdetecting as Urdu). Minimal change — no alignment model switching, no transliteration.
> 
> **Deliverables**:
> - `language` field on `SyncRequest` and `SyncResult`
> - `--language` CLI flag
> - Language passed to WhisperX `transcribe()`
> - Cache key includes language (correctness fix)
> - Tests for all changes
> 
> **Estimated Effort**: Quick
> **Parallel Execution**: NO — single task, sequential file edits
> **Critical Path**: models → aligner → pipeline → cache → CLI → tests

---

## Context

### Original Request
User ran `.venv/bin/python -m syncer "Seedhe Maut - 11K"` (Hindi rap song) and got Urdu-script output. Whisper auto-detected language as Urdu since Hindi and Urdu are phonetically identical (spoken Hindustani). User wants to force Hindi detection.

### Interview Summary
**Key Discussions**:
- Three layers of problems identified: (1) language detection, (2) alignment model, (3) script mismatch
- User chose **minimal fix** — just add language parameter, don't change alignment model or add transliteration
- Accepted limitations: English alignment model stays (noisy but functional for Hindi), snap-to-lyrics won't match Devanagari vs romanized LRCLIB lyrics

**Research Findings**:
- WhisperX `transcribe()` accepts `language: Optional[str]` — if None, auto-detects from first 30s
- WhisperX returns `{"segments": [...], "language": "hi"}` — detected language always in result
- Hindi alignment model exists (`theainerd/Wav2Vec2-large-xlsr-hindi`) but NOT in scope
- LRCLIB has Hindi lyrics in **romanized** Latin script — cross-script Levenshtein match = 0.000
- English wav2vec2 maps Devanagari chars to wildcards — alignment is noisy but doesn't crash

### Metis Review
**Identified Gaps** (addressed):
- **CRITICAL**: Cache key (`title|artist|duration`) does not include language → same song cached once returns wrong result for different language requests. Fix: add language to cache key.
- **HIGH**: `align()` returns `list[AlignedWord]` — no way to carry detected language back. Fix: return `AlignmentResult` dataclass.
- **HIGH**: WhisperX does no language code validation — invalid codes cause cryptic errors. Fix: validate in aligner.
- **MEDIUM**: Existing test assertions check exact `transcribe()` call args — will break when adding `language=`. Fix: update assertions.

---

## Work Objectives

### Core Objective
Add an optional `language` parameter that flows from user input (CLI/API) through the pipeline to WhisperX's `transcribe()` call, so users can force correct language detection for non-English songs.

### Concrete Deliverables
- `SyncRequest.language: str | None` field
- `SyncResult.detected_language: str | None` field
- `--language` / `-l` CLI argument
- `AlignmentResult` dataclass wrapping words + detected language
- Language-aware cache key in `generate_track_id()`
- Language validation before WhisperX call
- Tests covering all new behavior

### Definition of Done
- [ ] `python -m syncer --language hi "Seedhe Maut - 11K"` passes `language="hi"` to WhisperX
- [ ] `SyncResult` JSON output includes `"detected_language": "hi"`
- [ ] Same song cached with different languages produces different cache entries
- [ ] All 170+ existing tests still pass
- [ ] New tests for language threading, validation, and cache isolation

### Must Have
- Optional `language` field on SyncRequest (default None = auto-detect)
- Language threaded to `whisperx.transcribe(language=...)`
- Detected language stored in SyncResult
- Language included in cache key
- Language code validation (ISO 639-1, reject invalid)
- `--language` CLI flag
- Backward compatible — no language = existing behavior

### Must NOT Have (Guardrails)
- NO alignment model switching — keep `language_code="en"` hardcoded in `__init__`
- NO transliteration library — accept cross-script snap failures
- NO changes to `snap.py` or `demucs_separator.py`
- NO LRCLIB duration fix (separate issue)
- NO VAD threshold tuning for Hindi
- NO importing from `whisperx.utils` in models.py — keep validation self-contained
- NO making `--language` required — must stay optional

---

## Verification Strategy (MANDATORY)

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES (pytest, 170 tests)
- **Automated tests**: Tests-after (match existing pattern)
- **Framework**: pytest (existing)

### QA Policy
Every change verified by updated/new unit tests + regression suite.

---

## Execution Strategy

### Single Wave (small feature, all sequential)

```
Wave 1 (Sequential — 1 task):
└── Task 1: Add language parameter through entire pipeline [unspecified-high]

Wave FINAL (After Task 1):
└── F1: Regression verification [quick]
```

---

## TODOs

- [ ] 1. Add language parameter through entire pipeline

  **What to do**:
  
  **Step 1 — Models** (`src/syncer/models.py`):
  - Add `language: str | None = None` to `SyncRequest`
  - Add `detected_language: str | None = None` to `SyncResult`
  
  **Step 2 — Aligner** (`src/syncer/alignment/whisperx_aligner.py`):
  - Add `AlignmentResult` dataclass: `words: list[AlignedWord]`, `detected_language: str`
  - Add language validation constant — a set of known ISO 639-1 codes from WhisperX's supported languages. The full set from `DEFAULT_ALIGN_MODELS_HF` and `DEFAULT_ALIGN_MODELS_TORCH` in `.venv/lib/python3.12/site-packages/whisperx/alignment.py` is: `{"en", "fr", "de", "es", "it", "ja", "zh", "nl", "uk", "pt", "ar", "cs", "ru", "pl", "hu", "fi", "fa", "el", "tr", "da", "he", "vi", "ko", "ur", "te", "hi", "ca", "ml", "no", "nn", "sk", "sl", "hr", "ro", "eu", "gl", "ka", "lv", "tl", "sv"}`. However, Whisper supports MORE languages for transcription than alignment. For this minimal fix, validate against the alignment set (since the alignment model stays English anyway, and we're just passing language to transcribe, we should accept ANY Whisper-supported language). Use a broader set or just validate it's a 2-letter lowercase string. Simplest: validate `len(language) == 2 and language.isalpha() and language.islower()`.
  - Change `align()` signature: `def align(self, audio_path: Path, language: str | None = None) -> AlignmentResult`
  - Pass `language` to `self.model.transcribe(audio, batch_size=8, language=language)`
  - Extract `detected_lang = result.get("language", language or "unknown")`
  - Return `AlignmentResult(words=words, detected_language=detected_lang)`
  
  **Step 3 — Pipeline** (`src/syncer/pipeline.py`):
  - In `sync()`, extract `language = request.language`
  - Change the `align()` call (currently line ~191): `alignment_result = self.aligner.align(vocals_path, language=language)`
  - Extract: `asr_words = alignment_result.words`
  - Store: `detected_language = alignment_result.detected_language`
  - Add `detected_language=detected_language` to the `SyncResult(...)` constructor
  - **IMPORTANT**: Also handle the audio extraction failure path (line ~123-131) — set `detected_language=None` there since alignment wasn't run
  
  **Step 4 — Cache** (`src/syncer/cache.py`):
  - Update `generate_track_id()` signature: add `language: str | None = None` parameter
  - Update key: `f"{title.lower().strip()}|{artist.lower().strip()}|{round(duration or 0)}|{language or 'auto'}"`
  - Update all 3 call sites:
    - `get_cached()` at line 60 — needs language param passed in
    - `store_result()` at line 93 — needs to extract language from result
  - Update `get_cached()` signature: add `language: str | None = None`
  - Update `store_result()`: extract language from `result` — use `result.detected_language` if available, else pass through from request. **Simplest approach**: add a `language` field to `SyncResult` (the request language, not detected) OR just pull from the result's detected_language. Use detected_language since that's what actually differentiates the cached result.
  
  **IMPORTANT CACHE DESIGN NOTE**: The cache key should use the **request language** (what the user asked for), not the detected language. Reason: if user passes `language=None` (auto-detect) and Whisper detects "hi", then later passes `language="hi"` explicitly, they should get different cache entries because auto-detect might produce different results next time. So the cache key uses `request.language or "auto"`. This means `get_cached()` and `store_result()` both need the request language.
  
  Simplest approach: pipeline passes `request.language` to both `get_cached()` and `store_result()`:
  - `get_cached(title, artist, duration, language=request.language)`
  - For `store_result()`, either pass language separately or store it on SyncResult. Since SyncResult already has `detected_language`, add a second field `request_language: str | None = None` OR just pass language as a separate arg to `store_result()`. The **cleanest** approach: `store_result(result, language=request.language)`. Update `store_result` to accept and use it.
  
  **Step 5 — CLI** (`src/syncer/__main__.py`):
  - Add argument: `parser.add_argument("--language", "-l", default=None, help="Force language code (ISO 639-1, e.g. 'hi' for Hindi, 'en' for English). Default: auto-detect.")`
  - Thread to SyncRequest: add `language=args.language` to all SyncRequest constructors (lines 43, 45, 50, 52)
  
  **Step 6 — API** (`src/syncer/api.py`):
  - NO code change needed — Pydantic auto-accepts the new `language` field from JSON body. Verify by reading the file to confirm `SyncRequest` is used directly as the request model.
  
  **Step 7 — Tests**:
  
  Update existing tests:
  - `tests/test_whisperx_aligner.py`: Update mock `transcribe` return values to include `"language": "en"` key. Update `assert_called_once_with` assertions to include `language=None`. Add new tests:
    - `test_align_passes_language_to_transcribe` — pass `language="hi"`, assert transcribe called with `language="hi"`
    - `test_align_returns_detected_language` — mock transcribe returning `{"language": "hi", "segments": [...]}`, assert `result.detected_language == "hi"`
    - `test_align_validates_language_code` — pass `language="xyz123"`, expect ValueError
    - `test_align_none_language_auto_detects` — pass `language=None`, assert transcribe called with `language=None`
  
  - `tests/test_pipeline.py`: Update `FakeAlignedWord` usage — `aligner.align()` now returns `AlignmentResult` not `list[AlignedWord]`. Update all mocks to return `AlignmentResult(words=[...], detected_language="en")`. Add:
    - `test_language_threaded_to_aligner` — pass `SyncRequest(title="x", language="hi")`, assert `aligner.align` called with `language="hi"` 
    - `test_detected_language_in_result` — verify `result.detected_language` is populated
  
  - `tests/test_cache.py`: Add:
    - `test_cache_key_includes_language` — verify different languages produce different track IDs
    - `test_cache_isolation_by_language` — store with language="hi", lookup with language=None should miss
  
  - `tests/test_cli.py`: Add:
    - `test_language_flag` — `["python", "-m", "syncer", "--language", "hi", "test"]` → verify SyncRequest has language="hi"
  
  - `tests/test_api.py`: Add:
    - `test_sync_with_language` — POST with `{"title": "test", "language": "hi"}` → verify language is passed through
  
  Run full regression: `.venv/bin/python -m pytest tests/ --ignore=tests/test_smoke.py --ignore=tests/test_e2e.py -q`

  **Must NOT do**:
  - Do NOT change `whisperx.load_align_model(language_code="en", ...)` — alignment model stays English
  - Do NOT add transliteration or change snap.py
  - Do NOT import from whisperx at the models.py level
  - Do NOT make --language required
  - Do NOT change existing test behavior — only add new tests and update broken assertions

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Touches 7+ files across model/pipeline/cache/CLI/tests — needs careful threading and regression awareness. Not visual, not ultra-complex, but needs precision.
  - **Skills**: []
    - No special skills needed — standard Python editing and testing.

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 1 (sole task)
  - **Blocks**: F1
  - **Blocked By**: None

  **References** (CRITICAL):

  **Pattern References**:
  - `src/syncer/alignment/whisperx_aligner.py:45-49` — Current `__init__` showing hardcoded `language_code="en"`. Do NOT change this.
  - `src/syncer/alignment/whisperx_aligner.py:51-97` — Current `align()` method. Change signature, add language param to transcribe call, wrap return in AlignmentResult.
  - `src/syncer/alignment/whisperx_aligner.py:14-21` — Existing `AlignedWord` dataclass. Model `AlignmentResult` similarly.
  - `src/syncer/pipeline.py:189-191` — Where `self.aligner.align(vocals_path)` is called. Update to unpack `AlignmentResult`.
  - `src/syncer/pipeline.py:169-181` — Where `SyncResult` is constructed. Add `detected_language=`.
  - `src/syncer/pipeline.py:122-131` — Audio extraction failure path — also constructs `SyncResult`, needs `detected_language=None`.
  - `src/syncer/cache.py:35-38` — `generate_track_id()` — add language to key string.
  - `src/syncer/cache.py:56-73` — `get_cached()` — add language param, pass to generate_track_id.
  - `src/syncer/cache.py:91-129` — `store_result()` — add language param, pass to generate_track_id.
  - `src/syncer/__main__.py:16-24` — Existing argparse arguments. Add `--language` after `--verbose`.
  - `src/syncer/__main__.py:42-52` — SyncRequest constructors. Add `language=args.language` to all 4.

  **API/Type References**:
  - `src/syncer/models.py:37-40` — `SyncRequest` model. Add `language: str | None = None`.
  - `src/syncer/models.py:28-35` — `SyncResult` model. Add `detected_language: str | None = None`.
  - `.venv/lib/python3.12/site-packages/whisperx/asr.py:197-208` — WhisperX `transcribe()` signature showing `language: Optional[str] = None` parameter.
  - `.venv/lib/python3.12/site-packages/whisperx/asr.py:295` — Return value `{"segments": segments, "language": language}`.

  **Test References**:
  - `tests/test_whisperx_aligner.py` — Mock patterns for whisperx. The `align()` tests mock `whisperx.load_audio`, `whisperx.load_model`, `whisperx.load_align_model`, `whisperx.align`. The `transcribe` mock is on the model instance: `mock_model.transcribe.return_value = {"segments": [...]}` — needs `"language": "en"` added.
  - `tests/test_pipeline.py:80-89` — Patch targets for mocking pipeline dependencies.
  - `tests/test_pipeline.py:182-186` — Mock setup for `align_cls.return_value.align.return_value`. Currently returns `list[FakeAlignedWord]`. Must now return a mock `AlignmentResult`.
  - `tests/test_cache.py` — 9 existing tests. Add language-aware tests following same pattern.
  - `tests/test_cli.py` — Uses `patch("sys.argv", ...)` pattern for testing CLI args.

  **Acceptance Criteria**:

  - [ ] `SyncRequest(title="test", language="hi").language == "hi"`
  - [ ] `SyncRequest(title="test").language is None`
  - [ ] `SyncResult(..., detected_language="hi").detected_language == "hi"`
  - [ ] `.venv/bin/python -m syncer --help` shows `--language` option
  - [ ] `generate_track_id("t", "a", 100, language="hi") != generate_track_id("t", "a", 100, language=None)`
  - [ ] All existing 170+ tests pass (regression)
  - [ ] New language-specific tests pass

  **QA Scenarios (MANDATORY):**

  ```
  Scenario: Language parameter threads to WhisperX transcribe
    Tool: Bash (pytest)
    Preconditions: All source changes complete
    Steps:
      1. Run: .venv/bin/python -m pytest tests/test_whisperx_aligner.py -v -k "language" -q
      2. Assert: All language tests pass, 0 failures
    Expected Result: 4+ tests pass covering language threading, detection, validation, None
    Failure Indicators: Any test fails or import errors
    Evidence: .sisyphus/evidence/task-1-aligner-language-tests.txt

  Scenario: Pipeline threads language from request to aligner and result
    Tool: Bash (pytest)
    Preconditions: All source changes complete
    Steps:
      1. Run: .venv/bin/python -m pytest tests/test_pipeline.py -v -k "language" -q
      2. Assert: All language pipeline tests pass
    Expected Result: 2+ tests pass covering language threading and detected_language in result
    Failure Indicators: Any test fails
    Evidence: .sisyphus/evidence/task-1-pipeline-language-tests.txt

  Scenario: Cache isolates different language requests
    Tool: Bash (pytest)
    Preconditions: All source changes complete
    Steps:
      1. Run: .venv/bin/python -m pytest tests/test_cache.py -v -k "language" -q
      2. Assert: Cache language tests pass
    Expected Result: 2+ tests pass covering key differentiation and isolation
    Failure Indicators: Same cache key for different languages
    Evidence: .sisyphus/evidence/task-1-cache-language-tests.txt

  Scenario: CLI --language flag works
    Tool: Bash (pytest)
    Preconditions: All source changes complete
    Steps:
      1. Run: .venv/bin/python -m pytest tests/test_cli.py -v -k "language" -q
      2. Assert: CLI language test passes
    Expected Result: 1+ tests pass
    Evidence: .sisyphus/evidence/task-1-cli-language-tests.txt

  Scenario: Full regression — all existing tests still pass
    Tool: Bash (pytest)
    Preconditions: All changes complete
    Steps:
      1. Run: .venv/bin/python -m pytest tests/ --ignore=tests/test_smoke.py --ignore=tests/test_e2e.py -q
      2. Assert: 170+ passed, 0 failed
    Expected Result: All existing tests pass plus new tests
    Failure Indicators: Any existing test fails (regression)
    Evidence: .sisyphus/evidence/task-1-regression.txt
  ```

  **Commit**: YES
  - Message: `feat(pipeline): add language parameter for Hindi/multi-language support`
  - Files: `src/syncer/models.py`, `src/syncer/alignment/whisperx_aligner.py`, `src/syncer/pipeline.py`, `src/syncer/cache.py`, `src/syncer/__main__.py`, `tests/test_*.py`
  - Pre-commit: `.venv/bin/python -m pytest tests/ --ignore=tests/test_smoke.py --ignore=tests/test_e2e.py -q`

---

## Final Verification Wave

- [ ] F1. **Regression + Smoke Check** — `quick`
  Run `.venv/bin/python -m pytest tests/ --ignore=tests/test_smoke.py --ignore=tests/test_e2e.py -q`. Verify 175+ passed (170 existing + 5+ new), 0 failed. Run `.venv/bin/python -m syncer --help` and verify `--language` appears. Run `python -c "from syncer.models import SyncRequest; print(SyncRequest(title='test', language='hi').language)"` and verify output is `hi`.
  Output: `Tests [PASS/FAIL] | CLI flag [PRESENT/MISSING] | Model field [WORKS/BROKEN] | VERDICT`

---

## Commit Strategy

- **Task 1**: `feat(pipeline): add language parameter for Hindi/multi-language support` — all changed files, `pytest` pre-commit

---

## Success Criteria

### Verification Commands
```bash
# All tests pass
.venv/bin/python -m pytest tests/ --ignore=tests/test_smoke.py --ignore=tests/test_e2e.py -q
# Expected: 175+ passed, 0 failed

# CLI flag exists
.venv/bin/python -m syncer --help 2>&1 | grep language
# Expected: Shows --language option

# Model field works
.venv/bin/python -c "from syncer.models import SyncRequest; print(SyncRequest(language='hi').language)"
# Expected: hi

# Cache key differentiates
.venv/bin/python -c "from syncer.cache import generate_track_id; print(generate_track_id('t','a',100,'hi') != generate_track_id('t','a',100,None))"
# Expected: True
```

### Final Checklist
- [ ] All "Must Have" present
- [ ] All "Must NOT Have" absent
- [ ] All tests pass (170+ existing + new)
- [ ] Backward compatible — no language param = existing auto-detect behavior

### Known Limitations (Accepted)
- English alignment model used for all languages — word timestamps noisy for non-English
- Snap-to-lyrics won't match Devanagari ASR output against romanized LRCLIB lyrics
- VAD thresholds not tuned for Hindi — some segments may be dropped
