# Pipeline Refactor — Learnings

## Codebase State (2026-03-08)
- `src/syncer/alignment/__init__.py` — currently EMPTY (0 bytes)
- `src/syncer/alignment/snap.py` — 352 lines, `compute_confidence()` at lines 330-352
- `src/syncer/alignment/whisperx_aligner.py` — 121 lines, `AlignedWord` + `AlignmentResult` dataclasses at lines 14-30
- `src/syncer/alignment/demucs_separator.py` — 126 lines, lazy-load pattern template
- `src/syncer/pipeline.py` — 373 lines; import at line 12: `from syncer.alignment.snap import snap_words_to_lyrics, compute_confidence`; aligner called at line ~191
- `src/syncer/config.py` — 17 lines; `whisperx_model`, `whisperx_device`, `whisperx_compute_type` at lines 10-12
- `pyproject.toml` — `python-Levenshtein` at line 12, add `uroman` in its place
- `tests/test_pipeline.py` — 751 lines; `_make_settings()` at lines 46-55 uses whisperx_* fields
- `tests/test_models.py` — 208 lines; Settings construction tests need updating
- `src/syncer/models.py` — `detected_language` and `language` fields already added (hindi-language-param plan done)
- `src/syncer/cache.py` — `generate_track_id()` already accepts `language` param (hindi plan done)

## MMS_FA Critical Facts
- Labels vocab: `('-', 'a', 'i', 'e', 'n', 'o', 'u', 't', 's', 'r', 'm', 'k', 'l', 'd', 'g', 'h', 'y', 'b', 'p', 'w', 'c', 'v', 'j', 'z', 'f', "'", 'q', 'x', '*')`
- ONLY these 29 characters are safe — tokenizer CRASHES on uppercase, digits, most punctuation
- Sample rate: 16000 Hz, mono
- Frame rate: ~49fps (20.4ms/frame)
- Frame → seconds: `frame_index * 320 / 16000`

## New timing_source values
- `"ctc_aligned"` — replaces "lrclib_enhanced" and "whisperx_only"
- `"lrclib_synced"` — kept (LRCLIB line timestamps, no word-level)
- `"no_lyrics"` — new (graceful skip when LRCLIB has nothing)

## Parallelization Decision
Tasks 1 and 4 write to same files (text_normalize.py + test_text_normalize.py).
Decision: Combine 1+4 into single delegation, run alongside Tasks 2 and 3.
Wave 1 effective: 3 parallel streams: (Task1+4), Task2, Task3

## Task 1+4: Text Normalization Module (2026-03-08)

### uroman Library API
- Package: `uroman==1.3.1.1` (pip/uv installable)
- API: `from uroman import Uroman; u = Uroman(); u.romanize_string(text)`
- NOT `uroman.romanize()` — it's a class method on `Uroman` instance
- Works for Hindi→namaste, Japanese→konnichiha, Cyrillic→Privet, Arabic→mrhba
- `dir(uroman)` shows: `RomFormat`, `Uroman`, `uroman` (submodule)

### Normalization Pipeline Order
- romanize → lowercase → strip digits → strip non-safe chars → split → filter empties
- MMS_FA safe chars: `a-z`, `'`, `-`, space (confirmed from task spec)
- Digits must be removed BEFORE punctuation strip (so "24K" → "K" → "k")
- Hyphen in regex character class must be escaped or placed at end: `[^a-z'\-\s]`

### Test Patterns
- 29 tests total: 17 normalize, 9 romanize, 2 fallback, 1 integration
- Mock `_get_uroman_instance` returning None to test fallback path
- `patch.dict("sys.modules", {"uroman": None})` alone isn't enough — need to mock the cached instance getter

### Environment
- No `pip` in venv, use `uv pip install` or `.venv/bin/python3 -m uv pip`
- Python 3.12.8 in .venv
- basedpyright LSP not installed (non-blocking)

## Task 2: Relocate compute_confidence()

**Completed**: compute_confidence() successfully moved from snap.py to alignment/__init__.py

**Key learnings**:
- Function copied exactly (lines 330-352 from snap.py)
- Added required import: `from syncer.models import SyncedLine` to __init__.py
- Updated pipeline.py line 12 to split imports: snap_words_to_lyrics stays in snap, compute_confidence now from alignment
- Test results: 210 passed, 1 pre-existing failure (unrelated Settings test)
- Verification: `from syncer.alignment import compute_confidence` works, returns 0.0 for empty list
- snap.py still contains original compute_confidence (will be removed in Task 8)

**Pattern**: When relocating functions, ensure all type dependencies are imported in the new location.

## Task 3: Config Cleanup (2026-03-08)

**Completed**: Config fields refactored from whisperx_* to ctc_*

**Changes**:
- `src/syncer/config.py`: Removed `whisperx_model`, `whisperx_device`, `whisperx_compute_type`; added `ctc_device: str = "cpu"` and `ctc_model: str = "MMS_FA"`
- `pyproject.toml`: Replaced `python-Levenshtein` with `uroman` (line 12)
- `tests/test_pipeline.py`: Updated `_make_settings()` to remove whisperx_* kwargs
- `tests/test_models.py`: Updated TestSettings assertions to use ctc_* fields; updated env override test
- `tests/test_smoke.py`: Removed `"whisperx_model": "base"` from evidence dict
- `src/syncer/pipeline.py`: Updated `SyncPipeline.__init__()` to pass `ctc_model` and `ctc_device` to WordAligner (compute_type uses default)

**Key Insight**: Settings has `extra="ignore"`, so old whisperx_* kwargs are silently dropped. WordAligner still uses whisperx internally (Task 7 work).

**Test Results**: 210 passed, 1 pre-existing failure (spotify_client_id env var). All pipeline tests now pass (previously 12 failures).

**Verification**: `Settings().ctc_device == "cpu"` and `Settings().ctc_model == "MMS_FA"` ✓

## Task 5: CTCAligner Module (2026-03-08)

**Completed**: CTCAligner with full mocked test suite, TDD approach.

### MMS_FA API (Verified)
- `bundle.get_model()` returns `_Wav2Vec2Model` — call with `model(waveform)` returns `(emission_tensor, None)` tuple
- `bundle.get_tokenizer()` returns `Tokenizer` — `tokenizer(["hello", "world"])` → `[[15, 3, 12, 12, 5], [19, 5, 9, 12, 13]]`
- `bundle.get_aligner()` returns `Aligner` — `aligner(emission[0], tokens)` where tokens is `List[List[int]]` (per-word, NOT flat)
- Aligner returns `List[List[TokenSpan]]` — one list of TokenSpans per word
- `TokenSpan` has fields: `token, start, end, score`
- Emission shape for 1s audio: `(1, 49, 29)` — 49 frames, 29 tokens (labels)
- **CRITICAL**: `model.to(device)` returns self in real code, but MagicMock returns a new mock. Must set `mock_model.to = MagicMock(return_value=mock_model)` in tests.

### Implementation Details
- Lazy loading: `_model = None` in `__init__`, loaded in `_load_model()` on first `align()` call
- Frame→seconds: `frame_index * 320 / 16000`
- Word scores: average of character-level span scores
- Empty lyrics short-circuit before audio load
- Stereo→mono via `waveform.mean(dim=0, keepdim=True)`
- Resample via `torchaudio.transforms.Resample`

### Test Structure
- 18 tests in 4 groups: structure (3), dataclasses (4), align method (8), normalization (3)
- All tests mock torchaudio — no model download needed
- Helper `_make_mock_bundle(num_words)` creates consistent fake bundle

## Task 6: CTC Smoke Test Results
- Full pipeline (YouTube download → Demucs → CTC alignment) works end-to-end
- 135 words aligned from 20 lyrics lines of "Never Gonna Give You Up"
- Average CTC confidence score: 0.238 (low but expected for singing voice — MMS_FA trained on speech)
- First word "we're" starts at 18.76s — aligns well with the song's intro
- Total elapsed: ~136 seconds (YouTube DL ~1s, Demucs ~60s, CTC ~30s, rest is model loading)
- Last few words show alignment drift (e.g., "let" spans 115.92s–137.84s) — tail of lyrics aligns poorly
- Pipeline is wired correctly; quality improvements are for Task F3 QA

## Task 7: Pipeline Rewrite (2026-03-08)

**Completed**: pipeline.py rewritten from WhisperX+snap to CTCAligner, LRCLIB mandatory, graceful skip.

### Key Changes
- `pipeline.py`: Imports changed (CTCAligner, normalize_for_alignment), removed WordAligner/snap_words_to_lyrics
- `__init__`: `CTCAligner(device=settings.ctc_device)` — no model param needed
- New module-level `_build_synced_lines()` function regroups flat CTC words into SyncedLines by original lyric line
- Deleted `_lines_from_asr()` method entirely
- Graceful skip: `plain_lyrics_text is None` → immediately return `SyncResult(timing_source="no_lyrics", lines=[], confidence=0.0)`
- timing_source values: "ctc_aligned" (default/success), "lrclib_synced" (fallback), "no_lyrics" (skip)

### Test Changes
- 24 tests (was 22, added 3 graceful skip tests, removed some old tests)
- All `_P_SNAP` patches removed; `_P_ALIGNER` now targets `CTCAligner`
- Tests that previously had `mock_fetch.return_value = None` now either provide lyrics (to exercise full pipeline) or test graceful skip
- New `_make_alignment_result()` helper creates `AlignmentResult` with proper word counts
- YouTube metadata retry tests updated: first LRCLIB call returns plain lyrics (not None) so pipeline doesn't skip early

### Behavioral Changes
- LRCLIB is now mandatory: no lyrics → no audio extraction, immediate skip
- No more "whisperx_only" or "lrclib_enhanced" timing_source values
- `_build_synced_lines` handles CTC dropping words gracefully (Python slice doesn't raise on out-of-bounds)
- YouTube URLs with unknown titles + no LRCLIB lyrics → graceful skip (no longer attempts audio extraction)

## Task 8: Delete WhisperX and Snap Modules (2026-03-08)

**Completed**: Successfully removed obsolete WhisperX aligner and snap.py modules.

### Files Deleted
- `src/syncer/alignment/whisperx_aligner.py` (121 lines)
- `src/syncer/alignment/snap.py` (352 lines)
- `tests/test_whisperx_aligner.py` (12,137 bytes)
- `tests/test_snap.py` (7,895 bytes)

### Verification
- Dangling imports check: 0 matches for `whisperx_aligner` or `from syncer.alignment.snap` (excluding __pycache__)
- Test suite: 194 passed, 1 pre-existing failure (test_settings_defaults), 14 deselected
- No import errors introduced

### Key Insight
Task 7 (pipeline rewrite) successfully eliminated all dependencies on these modules:
- `pipeline.py` no longer imports from snap or whisperx_aligner
- `compute_confidence()` was already relocated to `src/syncer/alignment/__init__.py` in Task 2
- Safe to delete without breaking any functionality

### Commit
`chore: remove WhisperX aligner, snap.py, and associated tests` (commit b40093c)

## Task 10: Cache Clear Method (2026-03-08)

**Completed**: Added `clear_all()` method to CacheManager and created clear_cache.py script.

### Implementation Details
- `clear_all()` method in `src/syncer/cache.py`:
  - Returns `int` (count of entries cleared)
  - Deletes all rows from `sync_results` and `tracks` tables
  - Includes error handling with logging
  - Follows existing `_connect()` pattern for database access

### Script Details
- `scripts/clear_cache.py` created:
  - Imports CacheManager and Settings correctly
  - Displays before/after entry counts
  - Asserts final state is 0 entries
  - Idempotent: runs twice without error

### Test Results
- First run: Cleared 12 stale WhisperX-era entries
- Second run: 0 entries (idempotent, no crash)
- Final verification: `len(cache.list_tracks())` returns 0

### Key Insight
CacheManager uses sqlite3 directly (no ORM). The `_connect()` context manager pattern ensures proper connection handling. No schema changes needed — just DELETE operations on existing tables.

### Commit
`chore: add cache clear method and clear stale WhisperX-era entries` (commit 7833172)

## Task 9: Update Remaining Test Files (2026-03-08)

**Completed**: All test files updated to remove WhisperX references and use CTC alignment terminology.

### Files Changed
- `tests/test_smoke.py`: Replaced `test_whisperx_loads()` with `test_ctc_aligner_loads()` (uses `torchaudio.pipelines.MMS_FA`); rewrote `test_full_pipeline()` to use `CTCAligner` instead of whisperx; updated docstring
- `tests/test_e2e.py`: Updated `timing_source` assertion from `("lrclib_synced", "lrclib_enhanced", "whisperx_aligned", "whisperx_only")` to `("lrclib_synced", "ctc_aligned", "no_lyrics")`
- `tests/test_models.py`: Changed `timing_source="whisperx_only"` to `"ctc_aligned"` in `test_sync_result_with_optional_fields`
- `tests/test_cache.py`: Changed `timing_source="whisperx_aligned"` to `"ctc_aligned"` in `test_overwrite_existing_entry`

### Verification
- `grep -rn 'whisperx\|WhisperX\|whisper_x' tests/` → 0 matches
- 194 passed, 1 pre-existing failure (test_settings_defaults from .env), 14 deselected

### Key Insight
Settings tests (ctc_device, ctc_model) were already updated in Task 3. Only the timing_source strings and WhisperX imports/usage needed updating in Task 9.

---

## Final QA — End-to-End Pipeline Verification (Task F3, 2026-03-08)

### Results: 3/3 songs pass (with 2 bug workarounds)

| Song | Timing Source | Lines | Words | Confidence | Processing |
|------|--------------|-------|-------|------------|------------|
| Rick Astley - Never Gonna Give You Up | ctc_aligned | 58 | 364 | 0.124 | 128.7s |
| Bach - Toccata and Fugue in D minor | no_lyrics | 0 | 0 | 0.0 | <1s |
| Arijit Singh - Tum Hi Ho (Hindi) | ctc_aligned | 45 | 210 | 0.393 | 161.8s |

### Bugs Found

**BUG 1 — LRCLIB duration=0.0 → HTTP 400 (BLOCKS CLI)**
- `pipeline.py` passes `TrackInfo.duration=0.0` to `fetch_lyrics()`. LRCLIB rejects 0.0 as invalid.
- Fallback search only triggers on 404, not 400 → returns None → false `no_lyrics`.
- Fix: Treat `duration <= 0` as `None` in `fetch_lyrics()` or pipeline.

**BUG 2 — Hyphen in lyrics → blank CTC token → crash (BLOCKS ALIGNMENT)**
- `text_normalize._STRIP_PATTERN` keeps hyphens. MMS_FA tokenizer maps `-` to token 0 (blank).
- `torchaudio.forced_align()` raises ValueError when targets contain blank index.
- Fix: Remove `-` from `_STRIP_PATTERN` or replace with space before tokenization.

### Key Observations
- Hindi romanized lyrics aligned with HIGHER confidence (0.39) than English (0.12)
- MMS_FA may handle vowel-heavy romanized text better than English contractions
- All pipeline components (LRCLIB, YouTube DL, Demucs, CTC) work individually
- CLI is blocked by Bug 1 (duration=0.0) — every title/artist query fails at LRCLIB step
- Evidence saved to `.sisyphus/evidence/final-qa/`
