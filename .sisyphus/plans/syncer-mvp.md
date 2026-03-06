# Syncer MVP — Song-Synced Lyrics Service

## TL;DR

> **Quick Summary**: Build a Python service that takes a song URL (YouTube/Spotify) or title/artist query and returns synchronized lyrics with line-level and word-level timestamps as JSON. Uses LRCLIB for existing synced lyrics, with a Demucs + WhisperX alignment pipeline for songs that need word-level enhancement or have no pre-existing sync data.
> 
> **Deliverables**:
> - CLI tool: `python -m syncer <url_or_query>` → JSON to stdout
> - REST API: `POST /api/sync` → JSON response
> - SQLite cache for processed results
> - pytest test suite with 5 named reference songs
> 
> **Estimated Effort**: Medium
> **Parallel Execution**: YES — 5 waves + final verification
> **Critical Path**: Smoke Test → Data Models → Pipeline Orchestrator → API/CLI → E2E Tests

---

## Context

### Original Request
Build an MVP for a song-synced lyrics service based on a comprehensive research brief. The brief covers a 6-layer commercial system across 3 phases. This plan covers Phase 1 (Feasibility MVP) only.

### Interview Summary
**Key Discussions**:
- **Tech Stack**: Python backend (FastAPI) — no frontend for MVP. TS frontend deferred to future phase.
- **Music Sources**: YouTube for audio (yt-dlp), Spotify Web API for metadata/ISRC
- **Lyrics**: LRCLIB (primary, free, no auth, community synced LRC) + syncedlyrics Python package fallback
- **Alignment**: Text-first approach — use existing synced lyrics when available, run Demucs + WhisperX only when needed
- **Database**: SQLite for caching (zero setup, easy migration later)
- **Deployment**: Local development only (macOS). No Docker, no cloud.
- **Tests**: pytest after implementation + agent QA scenarios
- **Output**: Practical MVP schema — track info, lines with timestamps, words with timestamps, confidence
- **Scope**: English pop/rock/hip-hop only

**Research Findings**:
- **LRCLIB**: Free, no auth, no rate limits. Returns `syncedLyrics` (LRC) + `plainLyrics`. Best free lyrics source.
- **Demucs HTDemucs**: pip-installable, MIT, 34x realtime on M4 Max. Vocal isolation dramatically improves alignment quality.
- **WhisperX**: pip-installable, 19.9k stars. Word-level timestamps via wav2vec2 phoneme aligner. ~70-80% accuracy on singing.
- **Spotify API (Feb 2026)**: Dev mode limited to 5 users. ISRC still available. NO audio access, NO lyrics.
- **syncedlyrics package**: Aggregates LRCLIB + unofficial Musixmatch. Good coverage for popular tracks.
- **Snap-to-lyrics**: Hardest custom code — match ASR output to canonical lyrics text via Levenshtein/edit-distance alignment. Inspired by Kaldi's `align_ctm_ref.py`.
- **Key risk**: ML dependency installation on macOS ARM. Must validate before writing app code.

### Metis Review
**Identified Gaps** (addressed):
- **Wave 0 smoke test**: ML dependencies (torch, demucs, whisperx) must be validated on target Mac before any app code. This is the #1 project risk.
- **Snap-to-lyrics algorithm**: Was described too vaguely — now a dedicated task with concrete algorithm spec.
- **Named test songs**: MVP needs 5 specific songs as acceptance fixtures, not just "English pop."
- **Temp file cleanup**: All intermediate audio files must use `tempfile.TemporaryDirectory`.
- **Model preloading**: Demucs + WhisperX loaded once at startup, not per-request.
- **Sync API only**: No job queue, no polling, no WebSocket. Client blocks and waits.
- **Error handling**: Each pipeline step must fail gracefully with clear error messages.
- **Processing time**: Full pipeline is 60-120s per song on CPU. Documented, not hidden.

---

## Work Objectives

### Core Objective
Prove the end-to-end lyrics sync pipeline works: song input → synced lyrics JSON output with line and word timestamps.

### Concrete Deliverables
- `syncer` Python package with CLI and API entry points
- CLI: `python -m syncer <url_or_query>` prints JSON to stdout
- API: FastAPI app at `http://localhost:8000` with `POST /api/sync` and `GET /api/cache/{track_id}`
- SQLite database at `~/.syncer/cache.db` with cached results
- pytest suite covering all modules + 5 named end-to-end test songs

### Definition of Done
- [ ] `python -m syncer "https://youtube.com/watch?v=dQw4w9WgXcQ"` returns valid JSON with `lines[].words[].start`
- [ ] `curl -X POST http://localhost:8000/api/sync -H "Content-Type: application/json" -d '{"url":"..."}'` returns synced lyrics
- [ ] Second request for same song returns cached result in <500ms
- [ ] `pytest` passes with ≥80% of tests green
- [ ] 5 named reference songs produce valid, non-empty output

### Must Have
- Song input via YouTube URL, Spotify URL, or title/artist text query
- LRCLIB integration for pre-existing synced lyrics
- Demucs vocal isolation for audio preprocessing
- WhisperX word-level timestamp generation
- Snap-to-lyrics text alignment (match ASR to canonical lyrics)
- Line-level timestamps on every output
- Word-level timestamps when alignment confidence is sufficient
- Overall confidence score (0.0–1.0)
- SQLite caching of processed results
- CLI and REST API interfaces
- pytest test suite

### Must NOT Have (Guardrails)
- **No job queue / async processing** — sync API, client blocks and waits
- **No abstract base classes** for "future extensibility" (no `BaseLyricsProvider`, `BaseAligner`)
- **No plugin system** for lyrics sources or alignment engines
- **No Docker** infrastructure — local dev only
- **No retry logic or multi-path fallback orchestration** — if a step fails, return error
- **No authentication or rate limiting** on the API
- **No multiple output formats** — JSON only (no LRC, SRT, etc.)
- **No Spotify search disambiguation** — Spotify URL → metadata only, not a search engine
- **No enhanced/extended LRC parsing** — standard `[mm:ss.xx] text` only
- **No model fine-tuning** — use pretrained models as-is
- **No more than 2 levels of directory nesting**
- **No config management system** — pydantic-settings or plain env vars
- **No logging beyond Python stdlib `logging`**
- **No streaming/SSE/chunked responses** — full JSON result or error
- **No concurrent request processing** — one song at a time (ML models share memory)

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: NO (greenfield)
- **Automated tests**: YES (tests after implementation)
- **Framework**: pytest
- **Setup**: Included in Wave 0 smoke test task

### QA Policy
Every task includes agent-executed QA scenarios. Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **API endpoints**: Use Bash (curl) — send requests, assert status + response fields
- **CLI commands**: Use Bash — run command, validate JSON output structure
- **ML pipeline**: Use Bash — process test audio, verify output files exist and are non-empty
- **Library modules**: Use Bash (python REPL) — import, call functions, compare output

### 5 Named Reference Songs (Acceptance Test Fixtures)
These specific songs define "does the MVP work?":

| # | Song | Artist | Why | Expected Behavior |
|---|------|--------|-----|-------------------|
| 1 | "Never Gonna Give You Up" | Rick Astley | Clean pop, LRCLIB likely has synced | Line + word timestamps from LRCLIB + alignment |
| 2 | "Shake It Off" | Taylor Swift | Modern pop, clear vocals | Good WhisperX accuracy on isolated vocals |
| 3 | "Lose Yourself" | Eminem | Fast rap stress test | Word alignment challenged, lower confidence expected |
| 4 | "Yesterday" | The Beatles | Simple, short, clean | Near-perfect alignment expected |
| 5 | "Bohemian Rhapsody" | Queen | Complex structure, tempo changes | Multi-section handling, partial confidence |

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 0 (BLOCKING — must pass before anything else):
└── Task 1: ML Smoke Test + Project Scaffolding [deep]

Wave 1 (After Wave 0 — foundation, 5 parallel):
├── Task 2: Data Models + Pydantic Schemas [quick]
├── Task 3: LRCLIB Client + LRC Parser [quick]
├── Task 4: Spotify Metadata Client [quick]
├── Task 5: YouTube Audio Extractor (yt-dlp) [quick]
└── Task 6: SQLite Cache Layer [quick]

Wave 2 (After Wave 1 — ML + alignment modules, 3 parallel):
├── Task 7: Demucs Vocal Isolation Module [unspecified-high]
├── Task 8: WhisperX Word Alignment Module [unspecified-high]
└── Task 9: Snap-to-Lyrics Text Matching + Confidence [deep]

Wave 3 (After Wave 2 — integration, 10 first then 11+12 parallel):
├── Task 10: Sync Pipeline Orchestrator [deep]
├── Task 11: FastAPI REST API [unspecified-high]
└── Task 12: CLI Interface [quick]

Wave 4 (After Wave 3 — end-to-end testing):
└── Task 13: End-to-End Tests with Reference Songs [unspecified-high]

Wave FINAL (After ALL tasks — independent review, 4 parallel):
├── Task F1: Plan Compliance Audit [oracle]
├── Task F2: Code Quality Review [unspecified-high]
├── Task F3: Real QA with Reference Songs [unspecified-high]
└── Task F4: Scope Fidelity Check [deep]

Critical Path: Task 1 → Task 2 → Task 7/8/9 → Task 10 → Task 11 → Task 13 → F1-F4
Parallel Speedup: ~60% faster than sequential
Max Concurrent: 5 (Wave 1)
```

### Dependency Matrix

| Task | Depends On | Blocks | Wave |
|------|-----------|--------|------|
| 1 | — | 2-6 | 0 |
| 2 | 1 | 7, 8, 9, 10 | 1 |
| 3 | 1 | 9, 10 | 1 |
| 4 | 1 | 10 | 1 |
| 5 | 1 | 7, 10 | 1 |
| 6 | 1 | 10, 11 | 1 |
| 7 | 2, 5 | 10 | 2 |
| 8 | 2 | 10 | 2 |
| 9 | 2, 3 | 10 | 2 |
| 10 | 3-9 | 11, 12, 13 | 3 |
| 11 | 6, 10 | 13 | 3 |
| 12 | 10 | 13 | 3 |
| 13 | 11, 12 | F1-F4 | 4 |
| F1-F4 | 13 | — | FINAL |

### Agent Dispatch Summary

- **Wave 0**: **1** — T1 → `deep`
- **Wave 1**: **5** — T2 → `quick`, T3 → `quick`, T4 → `quick`, T5 → `quick`, T6 → `quick`
- **Wave 2**: **3** — T7 → `unspecified-high`, T8 → `unspecified-high`, T9 → `deep`
- **Wave 3**: **3** — T10 → `deep`, T11 → `unspecified-high`, T12 → `quick`
- **Wave 4**: **1** — T13 → `unspecified-high`
- **FINAL**: **4** — F1 → `oracle`, F2 → `unspecified-high`, F3 → `unspecified-high`, F4 → `deep`

---

## TODOs

- [x] 1. ML Smoke Test + Project Scaffolding

  **What to do**:
  - Create project with `uv init syncer` — set up `pyproject.toml` with Python 3.11+
  - Add core dependencies: `fastapi`, `uvicorn`, `pydantic`, `pydantic-settings`, `httpx`, `yt-dlp`
  - Add ML dependencies: `torch`, `torchaudio`, `demucs`, `whisperx` (install from GitHub: `pip install git+https://github.com/m-bain/whisperX.git`)
  - Add test dependencies: `pytest`, `pytest-asyncio`
  - Create directory structure:
    ```
    syncer/
    ├── pyproject.toml
    ├── src/
    │   └── syncer/
    │       ├── __init__.py      # version = "0.1.0"
    │       ├── __main__.py      # CLI entry
    │       ├── models.py        # Pydantic schemas
    │       ├── config.py        # Settings
    │       ├── cache.py         # SQLite
    │       ├── api.py           # FastAPI app
    │       ├── pipeline.py      # Orchestrator
    │       ├── clients/
    │       │   ├── __init__.py
    │       │   ├── lrclib.py
    │       │   ├── spotify.py
    │       │   └── youtube.py
    │       └── alignment/
    │           ├── __init__.py
    │           ├── demucs_separator.py
    │           ├── whisperx_aligner.py
    │           └── snap.py
    └── tests/
        ├── conftest.py
        └── test_smoke.py
    ```
  - Run smoke test: load Demucs `htdemucs` model + WhisperX `large-v2` model on target Mac
  - Process a 30-second test audio clip through: Demucs separation → WhisperX transcription → WhisperX alignment
  - Verify: models load, output is non-empty, word timestamps exist in output
  - Monitor memory usage with `htop` — both models must coexist in RAM (<12GB combined)
  - If `large-v2` is too large for local dev, fall back to `base` or `small` and document the decision

  **Must NOT do**:
  - Do NOT create Docker files
  - Do NOT set up CI/CD
  - Do NOT create abstract base classes or plugin architecture
  - Do NOT install Apple Music or other platform SDKs

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: ML dependency troubleshooting on macOS ARM is notoriously tricky. Needs patience and problem-solving.
  - **Skills**: []
  - **Skills Evaluated but Omitted**:
    - `playwright`: No browser interaction needed

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 0 (solo — BLOCKS everything)
  - **Blocks**: Tasks 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13
  - **Blocked By**: None (first task)

  **References**:

  **Pattern References**:
  - WhisperX installation: `pip install git+https://github.com/m-bain/whisperX.git` — requires ffmpeg installed
  - Demucs installation: `pip install demucs` — requires torch + torchaudio
  - PyTorch on macOS ARM: use `pip install torch torchaudio` (MPS backend auto-detected)

  **API/Type References**:
  - WhisperX API: `whisperx.load_model("large-v2", device, compute_type="float32")` for CPU; `"float16"` for GPU
  - Demucs API: `from demucs.api import Separator; sep = Separator(model="htdemucs", segment=None)`
  - WhisperX align: `whisperx.load_align_model(language_code="en", device=device)` then `whisperx.align(segments, model_a, metadata, audio, device)`

  **External References**:
  - WhisperX GitHub: https://github.com/m-bain/whisperX
  - Demucs GitHub: https://github.com/facebookresearch/demucs
  - uv docs: https://docs.astral.sh/uv/

  **WHY Each Reference Matters**:
  - WhisperX install is from Git, not PyPI — the executor needs to know this or install will fail
  - `compute_type="float32"` is mandatory for CPU — `float16` crashes on non-CUDA devices
  - Demucs `Separator` API avoids CLI subprocess overhead and gives direct tensor access

  **Acceptance Criteria**:
  - [ ] `python -c "import syncer"` succeeds
  - [ ] `python -c "import whisperx; import demucs"` succeeds
  - [ ] `python -c "from demucs.api import Separator; s=Separator(model='htdemucs')"` loads model without error
  - [ ] Smoke test script processes 30s audio → outputs word timestamps JSON
  - [ ] `pytest tests/test_smoke.py` passes

  **QA Scenarios (MANDATORY):**
  ```
  Scenario: ML dependencies import and model loading
    Tool: Bash
    Preconditions: Clean venv created, dependencies installed
    Steps:
      1. Run `python -c "import torch; print(torch.__version__); print('MPS' if torch.backends.mps.is_available() else 'CPU')"` — verify torch version and device
      2. Run `python -c "from demucs.api import Separator; s=Separator(model='htdemucs'); print('Demucs OK')"` — verify Demucs loads
      3. Run `python -c "import whisperx; m=whisperx.load_model('base', 'cpu', compute_type='float32'); print('WhisperX OK')"` — verify WhisperX loads (use 'base' for speed)
    Expected Result: All three commands succeed, print version/OK messages
    Failure Indicators: ImportError, CUDA/MPS errors, model download failures
    Evidence: .sisyphus/evidence/task-1-ml-imports.txt

  Scenario: End-to-end smoke test on sample audio
    Tool: Bash
    Preconditions: Models loaded, a 30-second test audio file available (download via yt-dlp from a public domain source)
    Steps:
      1. Download short audio: `yt-dlp -x --audio-format wav -o "test_audio.wav" "https://www.youtube.com/watch?v=dQw4w9WgXcQ"` (first 30s)
      2. Run Demucs: `python -c "from demucs.api import Separator; s=Separator(model='htdemucs'); o,sep=s.separate_audio_file('test_audio.wav'); print('Vocals shape:', sep['vocals'].shape)"` — verify vocal separation
      3. Run WhisperX on separated vocals: verify word-level timestamps returned with `score` fields
    Expected Result: Demucs produces vocals tensor, WhisperX returns segments with word timestamps
    Failure Indicators: OOM error, empty segments, missing `score` field in word output
    Evidence: .sisyphus/evidence/task-1-smoke-pipeline.json
  ```

  **Commit**: YES
  - Message: `feat(init): project scaffolding with ML smoke test`
  - Files: `pyproject.toml, src/syncer/__init__.py, src/syncer/__main__.py, tests/test_smoke.py, smoke_test.py`
  - Pre-commit: `python -c "import syncer; import whisperx; import demucs"`

---

- [x] 2. Data Models + Pydantic Schemas + Config

  **What to do**:
  - Create `src/syncer/models.py` with these Pydantic models:
    ```python
    class SyncedWord(BaseModel):
        text: str
        start: float  # seconds
        end: float    # seconds
        confidence: float  # 0.0-1.0

    class SyncedLine(BaseModel):
        text: str
        start: float
        end: float
        words: list[SyncedWord]

    class TrackInfo(BaseModel):
        title: str
        artist: str
        duration: float  # seconds
        isrc: str | None = None
        source_url: str | None = None
        spotify_id: str | None = None
        youtube_id: str | None = None

    class SyncResult(BaseModel):
        track: TrackInfo
        lines: list[SyncedLine]
        confidence: float  # overall 0.0-1.0
        timing_source: str  # 'lrclib_synced', 'lrclib_enhanced', 'whisperx_aligned', 'whisperx_only'
        cached: bool = False
        processing_time_seconds: float | None = None

    class SyncRequest(BaseModel):
        url: str | None = None
        title: str | None = None
        artist: str | None = None
    ```
  - Create `src/syncer/config.py` with pydantic-settings:
    ```python
    class Settings(BaseSettings):
        cache_dir: Path = Path.home() / ".syncer"
        db_path: Path = Path.home() / ".syncer" / "cache.db"
        whisperx_model: str = "base"  # or large-v2 for quality
        whisperx_device: str = "cpu"
        whisperx_compute_type: str = "float32"
        demucs_model: str = "htdemucs"
        spotify_client_id: str = ""
        spotify_client_secret: str = ""
        temp_dir: Path | None = None  # uses system temp if None
        max_song_duration: int = 600  # 10 min hard limit
    ```
  - Write tests in `tests/test_models.py`: validate model creation, serialization, JSON roundtrip

  **Must NOT do**:
  - Do NOT add segment structure (intro/verse/chorus) — deferred to Phase 2
  - Do NOT add syllable-level fields
  - Do NOT create abstract interfaces or protocol classes

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Straightforward Pydantic model definitions. No complex logic.
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 3, 4, 5, 6)
  - **Blocks**: Tasks 7, 8, 9, 10
  - **Blocked By**: Task 1

  **References**:

  **Pattern References**:
  - The research brief (lines 76-89) lists the ideal output fields — this model is a practical MVP subset

  **API/Type References**:
  - WhisperX output shape: `{"segments": [{"words": [{"word": str, "start": float, "end": float, "score": float}]}]}` — SyncedWord mirrors this
  - LRCLIB response: `{"syncedLyrics": "[00:17.12] line...", "plainLyrics": "line..."}` — SyncedLine maps from parsed LRC

  **External References**:
  - Pydantic v2 docs: https://docs.pydantic.dev/latest/
  - pydantic-settings: https://docs.pydantic.dev/latest/concepts/pydantic_settings/

  **WHY Each Reference Matters**:
  - WhisperX output shape defines the word-level schema — SyncedWord must be compatible for direct mapping
  - LRCLIB response shape defines what the LRC parser must produce to populate SyncedLine

  **Acceptance Criteria**:
  - [ ] `python -c "from syncer.models import SyncResult; print(SyncResult.model_json_schema())"` outputs valid JSON schema
  - [ ] `python -c "from syncer.config import Settings; s=Settings(); print(s.cache_dir)"` outputs path
  - [ ] `pytest tests/test_models.py` passes

  **QA Scenarios (MANDATORY):**
  ```
  Scenario: Model creation and JSON roundtrip
    Tool: Bash
    Preconditions: syncer package installed
    Steps:
      1. Run `python -c "from syncer.models import SyncedWord, SyncedLine, SyncResult, TrackInfo; w=SyncedWord(text='hello', start=1.0, end=1.5, confidence=0.9); l=SyncedLine(text='hello world', start=1.0, end=2.0, words=[w]); t=TrackInfo(title='Test', artist='Test', duration=180.0); r=SyncResult(track=t, lines=[l], confidence=0.9, timing_source='whisperx_aligned'); print(r.model_dump_json(indent=2))"` 
      2. Verify JSON output contains: track.title='Test', lines[0].words[0].text='hello', confidence=0.9
    Expected Result: Valid JSON with all fields populated, no validation errors
    Failure Indicators: ValidationError, missing fields, incorrect types
    Evidence: .sisyphus/evidence/task-2-model-roundtrip.json

  Scenario: Settings with defaults and env override
    Tool: Bash
    Preconditions: syncer package installed
    Steps:
      1. Run `python -c "from syncer.config import Settings; s=Settings(); print(s.db_path, s.whisperx_model, s.max_song_duration)"` — verify defaults
      2. Run `SYNCER_WHISPERX_MODEL=large-v2 python -c "from syncer.config import Settings; s=Settings(); assert s.whisperx_model=='large-v2'; print('Override OK')"` — verify env override
    Expected Result: Defaults are ~/.syncer/cache.db, base, 600. Env override changes model.
    Failure Indicators: Wrong defaults, env override ignored
    Evidence: .sisyphus/evidence/task-2-settings.txt
  ```

  **Commit**: YES (groups with Tasks 3-6)
  - Message: `feat(models): add Pydantic data models and config`
  - Files: `src/syncer/models.py, src/syncer/config.py, tests/test_models.py`
  - Pre-commit: `pytest tests/test_models.py`

---

- [x] 3. LRCLIB Client + LRC Parser

  **What to do**:
  - Create `src/syncer/clients/lrclib.py`:
    - Function `fetch_lyrics(title: str, artist: str, duration: float | None = None) -> LrcLibResult | None`
    - Use `httpx` (async-capable, but sync for MVP) to call:
      - `GET https://lrclib.net/api/get?track_name={title}&artist_name={artist}&duration={duration}` (primary, exact match)
      - `GET https://lrclib.net/api/search?track_name={title}&artist_name={artist}` (fallback, fuzzy)
    - Parse response: extract `syncedLyrics`, `plainLyrics`, `duration`, `trackName`, `artistName`
    - Handle: 404 (no lyrics), timeouts (5s), malformed responses, `instrumental: true`
  - LRC Parser function `parse_lrc(lrc_text: str) -> list[SyncedLine]`:
    - Parse standard LRC format: `[mm:ss.xx] text` → `SyncedLine(text=text, start=timestamp, end=next_line_start, words=[])`
    - Handle: empty lines, metadata tags like `[ti:Title]`, multiple timestamps per line (ignore extras)
    - Set `end` of each line to `start` of next line (last line: `start + 5.0`)
    - Words array is EMPTY at this stage — word-level comes from alignment pipeline
  - Write tests in `tests/test_lrclib.py`: mock HTTP responses, test LRC parsing edge cases

  **Must NOT do**:
  - Do NOT parse enhanced/extended LRC (word-level timing in LRC format)
  - Do NOT implement `syncedlyrics` package integration here — that's a fallback, not primary
  - Do NOT cache responses here — caching is in Task 6

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: HTTP client + string parsing. No complexity.
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 2, 4, 5, 6)
  - **Blocks**: Tasks 9, 10
  - **Blocked By**: Task 1

  **References**:

  **API/Type References**:
  - LRCLIB API docs: `GET /api/get?track_name=X&artist_name=Y&duration=Z` — returns `{id, trackName, artistName, albumName, duration, instrumental, plainLyrics, syncedLyrics}`
  - LRCLIB search: `GET /api/search?track_name=X&artist_name=Y` — returns array of results
  - Duration matching: LRCLIB matches within ±2 seconds of provided duration

  **External References**:
  - LRCLIB API docs: https://lrclib.net/docs
  - LRC format: standard `[mm:ss.xx] text` per line, metadata tags `[ti:Title]`, `[ar:Artist]`

  **WHY Each Reference Matters**:
  - The `duration` parameter is crucial — without it, LRCLIB may return lyrics for wrong version of same song
  - The `search` fallback is needed because `get` requires exact match and sometimes fails on slight title variations

  **Acceptance Criteria**:
  - [ ] `python -c "from syncer.clients.lrclib import fetch_lyrics; r=fetch_lyrics('Yesterday', 'The Beatles'); print(r)"` returns lyrics data
  - [ ] `python -c "from syncer.clients.lrclib import parse_lrc; lines=parse_lrc('[00:17.12] Hello\n[00:19.50] World'); print(len(lines), lines[0].start)"` prints `2 17.12`
  - [ ] `pytest tests/test_lrclib.py` passes

  **QA Scenarios (MANDATORY):**
  ```
  Scenario: Fetch synced lyrics for known song
    Tool: Bash
    Preconditions: Network available
    Steps:
      1. Run `python -c "from syncer.clients.lrclib import fetch_lyrics; r=fetch_lyrics('Yesterday', 'The Beatles', 125.0); assert r is not None; assert r.synced_lyrics is not None; print('Lines:', r.synced_lyrics[:100])"` 
      2. Verify output contains LRC-formatted text with timestamps like `[00:xx.xx]`
    Expected Result: Non-None result with synced lyrics containing `[` timestamps
    Failure Indicators: None result, no syncedLyrics field, network timeout
    Evidence: .sisyphus/evidence/task-3-fetch-lyrics.txt

  Scenario: LRC parser handles edge cases
    Tool: Bash
    Preconditions: syncer package installed
    Steps:
      1. Run parser on normal LRC: `parse_lrc('[00:17.12] Hello\n[00:19.50] World')` — expect 2 lines, correct timestamps
      2. Run parser on LRC with metadata: `parse_lrc('[ti:Test]\n[00:01.00] First line')` — expect 1 line, metadata skipped
      3. Run parser on empty input: `parse_lrc('')` — expect empty list, no crash
    Expected Result: 2 lines → correct; metadata skipped; empty → empty list
    Failure Indicators: Crash on metadata tags, wrong timestamp parsing, exception on empty
    Evidence: .sisyphus/evidence/task-3-lrc-parser.txt
  ```

  **Commit**: YES (groups with Tasks 2, 4-6)
  - Message: `feat(clients): LRCLIB, Spotify, YouTube, and cache modules`
  - Files: `src/syncer/clients/lrclib.py, tests/test_lrclib.py`
  - Pre-commit: `pytest tests/test_lrclib.py`

---

- [x] 4. Spotify Metadata Client

  **What to do**:
  - Create `src/syncer/clients/spotify.py`:
    - Function `resolve_spotify_url(url: str) -> TrackInfo | None`:
      - Extract track ID from Spotify URL (`open.spotify.com/track/{id}` or `spotify:track:{id}`)
      - Call `GET https://api.spotify.com/v1/tracks/{id}` with client credentials auth
      - Map response to `TrackInfo`: title, artist(s), duration, ISRC, spotify_id
    - Function `get_client_token(client_id: str, client_secret: str) -> str`:
      - `POST https://accounts.spotify.com/api/token` with `grant_type=client_credentials`
      - Cache token until expiry
    - Handle: invalid URLs, expired tokens, rate limits (429), missing ISRC
    - If Spotify credentials are not configured, this client is simply skipped (not an error)
  - Write tests in `tests/test_spotify.py`: mock API responses, test URL parsing

  **Must NOT do**:
  - Do NOT build Spotify search by title/artist — only URL → metadata resolution
  - Do NOT fetch album art, genres, or audio features
  - Do NOT handle playlist URLs or album URLs — single tracks only

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Simple HTTP client with OAuth client credentials. Well-documented API.
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 2, 3, 5, 6)
  - **Blocks**: Task 10
  - **Blocked By**: Task 1

  **References**:

  **API/Type References**:
  - Spotify track endpoint: `GET /v1/tracks/{id}` → `{name, artists[{name}], duration_ms, external_ids.isrc}`
  - Client credentials: `POST /api/token` with `grant_type=client_credentials`, Basic auth header
  - URL patterns: `https://open.spotify.com/track/6rqhFgbbKwnb9MLmUQDhG6` or `spotify:track:6rqhFgbbKwnb9MLmUQDhG6`

  **External References**:
  - Spotify Web API: https://developer.spotify.com/documentation/web-api/reference/get-track
  - Client credentials flow: https://developer.spotify.com/documentation/web-api/tutorials/client-credentials-flow

  **WHY Each Reference Matters**:
  - ISRC from Spotify is the key cross-platform identifier — use it to match against LRCLIB and YouTube
  - Client credentials flow doesn't require user auth — simplest OAuth flow, no redirect needed

  **Acceptance Criteria**:
  - [ ] URL parsing extracts track ID correctly from both URL formats
  - [ ] `pytest tests/test_spotify.py` passes (with mocked responses)
  - [ ] When Spotify credentials are empty, client returns None gracefully (no crash)

  **QA Scenarios (MANDATORY):**
  ```
  Scenario: Parse Spotify URL and extract track ID
    Tool: Bash
    Preconditions: syncer package installed
    Steps:
      1. Run `python -c "from syncer.clients.spotify import parse_spotify_url; assert parse_spotify_url('https://open.spotify.com/track/6rqhFgbbKwnb9MLmUQDhG6')=='6rqhFgbbKwnb9MLmUQDhG6'; print('OK')"` 
      2. Run with URI format: `parse_spotify_url('spotify:track:6rqhFgbbKwnb9MLmUQDhG6')` → same ID
      3. Run with invalid URL: `parse_spotify_url('https://example.com')` → None
    Expected Result: Both formats return correct ID, invalid returns None
    Failure Indicators: Exception on invalid URL, wrong ID extraction
    Evidence: .sisyphus/evidence/task-4-spotify-url.txt

  Scenario: Graceful handling when no Spotify credentials
    Tool: Bash
    Preconditions: No SPOTIFY_CLIENT_ID/SECRET env vars set
    Steps:
      1. Run `python -c "from syncer.clients.spotify import resolve_spotify_url; r=resolve_spotify_url('https://open.spotify.com/track/abc123'); print('Result:', r)"` 
    Expected Result: Returns None without raising exception
    Failure Indicators: Unhandled exception, crash, authentication error bubble up
    Evidence: .sisyphus/evidence/task-4-spotify-no-creds.txt
  ```

  **Commit**: YES (groups with Tasks 2, 3, 5, 6)
  - Message: `feat(clients): LRCLIB, Spotify, YouTube, and cache modules`
  - Files: `src/syncer/clients/spotify.py, tests/test_spotify.py`
  - Pre-commit: `pytest tests/test_spotify.py`

---

- [x] 5. YouTube Audio Extractor (yt-dlp Wrapper)

  **What to do**:
  - Create `src/syncer/clients/youtube.py`:
    - Function `extract_audio(url: str, output_dir: Path) -> AudioResult`:
      - Use yt-dlp Python API (`yt_dlp.YoutubeDL`) to download audio as WAV
      - `ydl_opts`: `format='bestaudio/best'`, `postprocessors=[{'key': 'FFmpegExtractAudio', 'preferredcodec': 'wav'}]`, `outtmpl`
      - Return `AudioResult(audio_path=Path, title=str, duration=float, youtube_id=str)`
    - Function `parse_youtube_url(url: str) -> str | None`:
      - Extract video ID from: `youtube.com/watch?v=ID`, `youtu.be/ID`, `music.youtube.com/watch?v=ID`
    - Use `tempfile.TemporaryDirectory()` for downloads when no explicit output_dir given
    - Handle: invalid URLs, age-restricted videos, unavailable videos, region-locked content
    - Enforce `max_song_duration` from settings — reject videos >10 minutes
  - Write tests in `tests/test_youtube.py`: test URL parsing (no network), mock yt-dlp for download tests

  **Must NOT do**:
  - Do NOT download video — audio only
  - Do NOT handle playlists — single videos only
  - Do NOT store downloads permanently — use temp directories
  - Do NOT build YouTube search — URL input only

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: yt-dlp wrapper with URL parsing. Well-documented library.
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 2, 3, 4, 6)
  - **Blocks**: Tasks 7, 10
  - **Blocked By**: Task 1

  **References**:

  **API/Type References**:
  - yt-dlp Python API: `yt_dlp.YoutubeDL(opts).download([url])` or `.extract_info(url, download=True)`
  - Key options: `format`, `postprocessors`, `outtmpl`, `quiet`, `no_warnings`
  - Info dict: `info['title']`, `info['duration']`, `info['id']`

  **External References**:
  - yt-dlp GitHub: https://github.com/yt-dlp/yt-dlp
  - yt-dlp embedding: https://github.com/yt-dlp/yt-dlp#embedding-yt-dlp

  **WHY Each Reference Matters**:
  - Python API avoids subprocess overhead and gives structured metadata
  - `extract_info` with `download=False` can be used to check duration before downloading (enforce limit)

  **Acceptance Criteria**:
  - [ ] URL parsing works for youtube.com, youtu.be, music.youtube.com formats
  - [ ] Duration check rejects videos >10 minutes before downloading
  - [ ] `pytest tests/test_youtube.py` passes

  **QA Scenarios (MANDATORY):**
  ```
  Scenario: Parse various YouTube URL formats
    Tool: Bash
    Preconditions: syncer package installed
    Steps:
      1. `parse_youtube_url('https://www.youtube.com/watch?v=dQw4w9WgXcQ')` → 'dQw4w9WgXcQ'
      2. `parse_youtube_url('https://youtu.be/dQw4w9WgXcQ')` → 'dQw4w9WgXcQ'
      3. `parse_youtube_url('https://music.youtube.com/watch?v=dQw4w9WgXcQ')` → 'dQw4w9WgXcQ'
      4. `parse_youtube_url('https://example.com')` → None
    Expected Result: All valid formats return correct ID, invalid returns None
    Failure Indicators: Exception, wrong ID
    Evidence: .sisyphus/evidence/task-5-youtube-urls.txt

  Scenario: Audio extraction produces valid WAV file
    Tool: Bash
    Preconditions: yt-dlp and ffmpeg installed, network available
    Steps:
      1. Run `python -c "from syncer.clients.youtube import extract_audio; from pathlib import Path; import tempfile; d=tempfile.mkdtemp(); r=extract_audio('https://www.youtube.com/watch?v=dQw4w9WgXcQ', Path(d)); print(r.audio_path, r.duration)"` 
      2. Verify audio file exists at returned path and duration >0
    Expected Result: WAV file created, duration matches expected (~212s for this song)
    Failure Indicators: File not found, 0-byte file, yt-dlp error
    Evidence: .sisyphus/evidence/task-5-audio-extraction.txt
  ```

  **Commit**: YES (groups with Tasks 2, 3, 4, 6)
  - Message: `feat(clients): LRCLIB, Spotify, YouTube, and cache modules`
  - Files: `src/syncer/clients/youtube.py, tests/test_youtube.py`
  - Pre-commit: `pytest tests/test_youtube.py`

---

- [x] 6. SQLite Cache Layer

  **What to do**:
  - Create `src/syncer/cache.py`:
    - Use stdlib `sqlite3` (no ORM — overkill for 2 tables)
    - Schema (create on first access):
      ```sql
      CREATE TABLE IF NOT EXISTS tracks (
        id TEXT PRIMARY KEY,  -- hash of (title_lower, artist_lower, duration_rounded)
        title TEXT NOT NULL,
        artist TEXT NOT NULL,
        duration REAL,
        isrc TEXT,
        spotify_id TEXT,
        youtube_id TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
      );
      CREATE TABLE IF NOT EXISTS sync_results (
        track_id TEXT PRIMARY KEY REFERENCES tracks(id),
        result_json TEXT NOT NULL,  -- full SyncResult as JSON
        confidence REAL,
        timing_source TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
      );
      ```
    - Functions:
      - `get_cached(title: str, artist: str, duration: float | None) -> SyncResult | None`
      - `store_result(result: SyncResult) -> None`
      - `generate_track_id(title: str, artist: str, duration: float | None) -> str` — deterministic hash
    - Track ID: `hashlib.sha256(f"{title.lower().strip()}|{artist.lower().strip()}|{round(duration or 0)}".encode()).hexdigest()[:16]`
    - Store full `SyncResult.model_dump_json()` in `result_json` column — no need to normalize
    - DB file at `Settings.db_path` (~/.syncer/cache.db), create parent dirs on init
  - Write tests in `tests/test_cache.py`: use `:memory:` SQLite for tests

  **Must NOT do**:
  - Do NOT use SQLAlchemy or any ORM
  - Do NOT create more than 2 tables
  - Do NOT add migration system — drop and recreate for schema changes in MVP
  - Do NOT add full-text search or indexing beyond primary key

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Simple sqlite3 CRUD. No complex queries.
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with Tasks 2, 3, 4, 5)
  - **Blocks**: Tasks 10, 11
  - **Blocked By**: Task 1

  **References**:

  **API/Type References**:
  - `SyncResult.model_dump_json()` for serialization, `SyncResult.model_validate_json()` for deserialization
  - `hashlib.sha256` for track ID generation

  **External References**:
  - Python sqlite3 docs: https://docs.python.org/3/library/sqlite3.html

  **WHY Each Reference Matters**:
  - Storing full JSON blob avoids complex joins and makes cache reads fast (single query, single deserialize)
  - SHA256 hash as track ID ensures deterministic, collision-resistant cache keys

  **Acceptance Criteria**:
  - [ ] Store and retrieve SyncResult via cache functions
  - [ ] Same (title, artist, duration) input always produces same track_id
  - [ ] `pytest tests/test_cache.py` passes

  **QA Scenarios (MANDATORY):**
  ```
  Scenario: Store and retrieve cached result
    Tool: Bash
    Preconditions: syncer package installed
    Steps:
      1. Create a SyncResult, store it via `store_result()`, then retrieve via `get_cached()` with same title/artist/duration
      2. Verify retrieved result matches original: same lines, same confidence, `cached=True`
      3. Retrieve with slightly different title casing → should still match (case-insensitive)
    Expected Result: Round-trip works, case-insensitive matching works
    Failure Indicators: None on retrieval, data corruption, case sensitivity
    Evidence: .sisyphus/evidence/task-6-cache-roundtrip.txt

  Scenario: Cache miss returns None gracefully
    Tool: Bash
    Preconditions: Empty database
    Steps:
      1. Call `get_cached('Nonexistent Song', 'Nobody', 180.0)` on empty DB
    Expected Result: Returns None, no exception
    Failure Indicators: Exception, crash, non-None result
    Evidence: .sisyphus/evidence/task-6-cache-miss.txt
  ```

  **Commit**: YES (groups with Tasks 2, 3, 4, 5)
  - Message: `feat(clients): LRCLIB, Spotify, YouTube, and cache modules`
  - Files: `src/syncer/cache.py, tests/test_cache.py`
  - Pre-commit: `pytest tests/test_cache.py`

---

- [x] 7. Demucs Vocal Isolation Module

  **What to do**:
  - Create `src/syncer/alignment/demucs_separator.py`:
    - Class `VocalSeparator`:
      - `__init__(self, model_name: str = "htdemucs")` — loads model ONCE, stores as instance var
      - `separate(self, audio_path: Path, output_dir: Path) -> Path` — returns path to isolated vocals WAV
    - Use `demucs.api.Separator` Python API (NOT CLI subprocess):
      ```python
      from demucs.api import Separator
      separator = Separator(model=model_name, segment=None)
      origin, separated = separator.separate_audio_file(str(audio_path))
      # separated["vocals"] is a torch.Tensor
      # Save vocals to WAV using torchaudio.save()
      ```
    - Save separated vocals as WAV to `output_dir/vocals.wav`
    - Use `--two-stems vocals` equivalent: only extract vocals (faster than full 4-stem)
    - Handle: file not found, OOM errors (catch and return informative error), non-audio files
    - Memory cleanup after separation: `del separated; gc.collect(); torch.cuda.empty_cache()`
  - Write tests in `tests/test_demucs.py`: test with a short audio fixture (5-10s synthetic WAV)

  **Must NOT do**:
  - Do NOT use CLI subprocess — use Python API only
  - Do NOT fine-tune or modify the model
  - Do NOT keep separated stems other than vocals — discard drums/bass/other
  - Do NOT create a base class or interface for separators

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: ML library integration with memory management. Needs careful tensor handling.
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 8, 9)
  - **Blocks**: Task 10
  - **Blocked By**: Tasks 1, 2, 5

  **References**:

  **Pattern References**:
  - `liuzhao1225/YouDub-webui/youdub/step010_demucs_vr.py` — production Demucs API usage with proper tensor handling
  - `showlab/Paper2Video` — uses Demucs for source separation in pipeline

  **API/Type References**:
  - `demucs.api.Separator(model="htdemucs", segment=None)` — `segment=None` processes entire file (vs chunked)
  - `separator.separate_audio_file(path)` returns `(origin: torch.Tensor, separated: dict[str, torch.Tensor])`
  - `separated["vocals"]` shape: `(channels, samples)` — save with `torchaudio.save(path, tensor, sample_rate)`
  - `separator.samplerate` — get the model's expected sample rate for saving

  **External References**:
  - Demucs API source: https://github.com/facebookresearch/demucs/blob/main/demucs/api.py

  **WHY Each Reference Matters**:
  - `segment=None` is important: chunked processing can introduce artifacts at chunk boundaries for short files
  - Memory cleanup pattern is critical — without it, Demucs tensors stay in RAM and WhisperX may OOM
  - `separated["vocals"]` key name is exactly "vocals" (not "voice" or "singing")

  **Acceptance Criteria**:
  - [ ] `VocalSeparator` loads model without error
  - [ ] `separate()` produces a valid WAV file at the output path
  - [ ] Output WAV is non-silent (RMS > 0.001)
  - [ ] `pytest tests/test_demucs.py` passes

  **QA Scenarios (MANDATORY):**
  ```
  Scenario: Vocal separation produces valid output
    Tool: Bash
    Preconditions: Demucs model downloaded, test audio available from Task 1 smoke test
    Steps:
      1. Create VocalSeparator instance
      2. Run `separate(test_audio_path, output_dir)` 
      3. Verify returned path exists, file size > 0, is valid WAV
      4. Load with torchaudio and verify: not all zeros, shape has >1000 samples
    Expected Result: vocals.wav exists, is audible (non-zero RMS), correct sample rate
    Failure Indicators: FileNotFoundError, zero-byte file, all-zeros tensor, OOM
    Evidence: .sisyphus/evidence/task-7-vocal-separation.txt

  Scenario: Graceful OOM handling on large file
    Tool: Bash
    Preconditions: VocalSeparator loaded
    Steps:
      1. Attempt separation on a very long audio file (or simulate with low memory)
      2. Verify error is caught and returns informative message (not raw torch error)
    Expected Result: Clean error message mentioning memory or file size
    Failure Indicators: Unhandled exception, process killed, no error message
    Evidence: .sisyphus/evidence/task-7-oom-handling.txt
  ```

  **Commit**: YES (groups with Tasks 8, 9)
  - Message: `feat(alignment): Demucs, WhisperX, and snap-to-lyrics modules`
  - Files: `src/syncer/alignment/demucs_separator.py, tests/test_demucs.py`
  - Pre-commit: `pytest tests/test_demucs.py`

---

- [x] 8. WhisperX Word Alignment Module

  **What to do**:
  - Create `src/syncer/alignment/whisperx_aligner.py`:
    - Class `WordAligner`:
      - `__init__(self, model_name: str, device: str, compute_type: str)` — loads WhisperX transcription model + alignment model ONCE
      - `align(self, audio_path: Path) -> list[AlignedSegment]` — transcribe + align, return word timestamps
    - Internal pipeline:
      ```python
      # Step 1: Transcribe
      audio = whisperx.load_audio(str(audio_path))
      result = self.model.transcribe(audio, batch_size=16)
      
      # Step 2: Align (word-level)
      result = whisperx.align(
          result["segments"], self.align_model, self.align_metadata, audio, self.device
      )
      
      # Step 3: Memory cleanup
      gc.collect()
      if torch.cuda.is_available(): torch.cuda.empty_cache()
      
      # Step 4: Extract words with timestamps
      # result["segments"][i]["words"] = [{"word": str, "start": float, "end": float, "score": float}]
      ```
    - Define `AlignedSegment` and `AlignedWord` as simple dataclasses (or use models from Task 2)
    - Handle: empty transcription (no words detected), missing `score` field in some words, audio too short
    - Normalize word text: strip whitespace, lowercase for matching (preserve original for display)
  - Write tests in `tests/test_whisperx_aligner.py`: test with vocal audio from Demucs output or short speech sample

  **Must NOT do**:
  - Do NOT use Whisper API (OpenAI cloud) — local only
  - Do NOT implement speaker diarization
  - Do NOT try multiple model sizes — use the one from config
  - Do NOT create a base class for aligners

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: WhisperX has subtle API quirks (memory management, device handling, missing score fields). Needs careful implementation.
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 7, 9)
  - **Blocks**: Task 10
  - **Blocked By**: Tasks 1, 2

  **References**:

  **Pattern References**:
  - `showlab/Paper2Video/src/speech_gen.py` — clean WhisperX transcribe→align flow with proper memory management
  - WhisperX README: load_model → transcribe → load_align_model → align

  **API/Type References**:
  - `whisperx.load_model(model_name, device, compute_type=compute_type)` — returns model
  - `model.transcribe(audio, batch_size=16)` — returns `{"segments": [{"text": str, "start": float, "end": float}], "language": str}`
  - `whisperx.load_align_model(language_code="en", device=device)` — returns `(model_a, metadata)`
  - `whisperx.align(segments, model_a, metadata, audio, device)` — adds `words` to each segment
  - Word format: `{"word": str, "start": float, "end": float, "score": float}` — score is confidence 0.0-1.0
  - **IMPORTANT**: Some words may be missing `score` field — default to 0.0

  **External References**:
  - WhisperX GitHub: https://github.com/m-bain/whisperX
  - WhisperX issue #1247 — MFA vs WhisperX accuracy discussion

  **WHY Each Reference Matters**:
  - `gc.collect() + torch.cuda.empty_cache()` after alignment is critical — without it, next pipeline step (or next request) may OOM
  - Some words legitimately lack `score` (e.g., single-character words, non-verbal sounds) — must handle gracefully
  - `batch_size=16` is the default; on CPU, lower to 4-8 to avoid memory issues

  **Acceptance Criteria**:
  - [ ] `WordAligner` loads model and produces word timestamps from audio file
  - [ ] Output includes `start`, `end`, `score` for each word
  - [ ] Handles audio with no detected speech (returns empty list, no crash)
  - [ ] `pytest tests/test_whisperx_aligner.py` passes

  **QA Scenarios (MANDATORY):**
  ```
  Scenario: Word alignment on vocal audio
    Tool: Bash
    Preconditions: WhisperX model loaded, isolated vocals WAV from Task 7 available
    Steps:
      1. Create WordAligner with config settings
      2. Run `align(vocals_path)` 
      3. Verify: returns list with >0 segments, each segment has `words` list, each word has `start`, `end`, `score`
      4. Verify: word timestamps are monotonically increasing (start[i] <= start[i+1])
    Expected Result: Multiple words with timestamps, scores between 0-1, timestamps in order
    Failure Indicators: Empty output, missing score fields, timestamps out of order, OOM
    Evidence: .sisyphus/evidence/task-8-word-alignment.json

  Scenario: Handle silent/empty audio gracefully
    Tool: Bash
    Preconditions: A short silent WAV file (generate with: python -c "import numpy; ...")
    Steps:
      1. Create 5-second silent WAV file
      2. Run `align(silent_path)` 
    Expected Result: Returns empty list or list with no words, no exception
    Failure Indicators: Crash, exception, infinite loop
    Evidence: .sisyphus/evidence/task-8-silent-audio.txt
  ```

  **Commit**: YES (groups with Tasks 7, 9)
  - Message: `feat(alignment): Demucs, WhisperX, and snap-to-lyrics modules`
  - Files: `src/syncer/alignment/whisperx_aligner.py, tests/test_whisperx_aligner.py`
  - Pre-commit: `pytest tests/test_whisperx_aligner.py`

---

- [x] 9. Snap-to-Lyrics Text Matching + Confidence Scoring

  **What to do**:
  - Create `src/syncer/alignment/snap.py` — **this is the most critical custom code in the entire MVP**:
    - Function `snap_words_to_lyrics(asr_words: list[AlignedWord], lyrics_lines: list[str]) -> list[SyncedLine]`:
      - **Algorithm** (Levenshtein-based word alignment):
        1. Flatten all lyrics lines into a single word sequence: `lyrics_words = [(word, line_idx, word_idx) for ...]`
        2. Build ASR word sequence: `asr_sequence = [(word.text.lower().strip(), word) for word in asr_words]`
        3. Run edit-distance dynamic programming alignment (Smith-Waterman variant):
           - Match score: +2 if words match (case-insensitive), +1 if Levenshtein ratio > 0.7
           - Mismatch penalty: -1
           - Gap penalty: -1 (for insertions/deletions)
        4. Walk back the alignment matrix to get matched pairs: `(lyrics_word, asr_word)` or `(lyrics_word, None)` or `(None, asr_word)`
        5. For matched pairs: assign ASR word's timestamp to lyrics word
        6. For unmatched lyrics words: interpolate timestamp between nearest matched neighbors
        7. For unmatched ASR words (hallucinations): discard
        8. Group words back into SyncedLine objects based on original line structure
      - **Line-level timestamps**: `line.start = first_word.start`, `line.end = last_word.end`
      - **Confidence scoring**:
        - Per-word: `asr_word.score` if matched, `0.3` if interpolated
        - Per-line: average of word confidences
        - Overall: average of line confidences, weighted by line word count
    - Function `compute_confidence(lines: list[SyncedLine]) -> float` — overall track confidence
    - Handle edge cases:
      - ASR returns 0 words → return lines with timestamps all at 0, confidence 0
      - Lyrics has way more words than ASR → most words interpolated, low confidence
      - ASR has way more words than lyrics → many hallucinations discarded
  - Write tests in `tests/test_snap.py`: unit tests with known word pairs, edge cases

  **Must NOT do**:
  - Do NOT implement phonetic matching (Soundex, Metaphone) — too complex for MVP
  - Do NOT handle repeated chorus disambiguation — treat each occurrence independently
  - Do NOT match ad-libs or backing vocals
  - Do NOT use external NLP libraries for this — keep it self-contained with stdlib + Levenshtein

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: Core algorithmic challenge. Requires careful dynamic programming implementation and edge case handling. This module defines the product quality.
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 2 (with Tasks 7, 8)
  - **Blocks**: Task 10
  - **Blocked By**: Tasks 1, 2, 3

  **References**:

  **Pattern References**:
  - Kaldi's `align_ctm_ref.py` — production-grade Smith-Waterman alignment implementation for matching ASR to reference text
  - `nomadkaraoke/lyrics-transcriber` — open-source lyrics alignment project with similar snap-to-lyrics approach

  **API/Type References**:
  - Input ASR words: `[{"word": str, "start": float, "end": float, "score": float}]` from WhisperX
  - Input lyrics: `list[str]` — one string per line from LRCLIB plainLyrics or LRC text content
  - Output: `list[SyncedLine]` with populated `words` array and confidence scores

  **External References**:
  - Levenshtein distance: `pip install python-Levenshtein` for `Levenshtein.ratio()` (fast C implementation)
  - Smith-Waterman algorithm: standard bioinformatics DP alignment adapted for word sequences

  **WHY Each Reference Matters**:
  - Kaldi's implementation handles the exact same problem (ASR output vs reference transcript) and is battle-tested
  - `python-Levenshtein` is much faster than pure-Python implementations — matters when aligning 500+ word songs
  - The interpolation strategy for unmatched words is the key to perceived quality — evenly distribute time between matched neighbors

  **Acceptance Criteria**:
  - [ ] Perfect alignment: when ASR and lyrics match exactly, all words get correct timestamps
  - [ ] Partial alignment: when ASR has errors, matched words get timestamps, unmatched get interpolated
  - [ ] Empty ASR: returns lines with 0 timestamps and confidence 0
  - [ ] Confidence score: higher when more words match, lower when more interpolation needed
  - [ ] `pytest tests/test_snap.py` passes

  **QA Scenarios (MANDATORY):**
  ```
  Scenario: Perfect word alignment (ASR matches lyrics exactly)
    Tool: Bash
    Preconditions: syncer package installed
    Steps:
      1. Create test data: asr_words = [{word:'hello', start:1.0, end:1.5, score:0.95}, {word:'world', start:1.6, end:2.0, score:0.90}], lyrics = ['hello world']
      2. Run snap_words_to_lyrics(asr_words, lyrics)
      3. Verify: output has 1 line, 2 words, timestamps match ASR, confidence > 0.9
    Expected Result: Line with start=1.0, end=2.0, both words correctly mapped
    Failure Indicators: Wrong timestamps, missing words, confidence too low
    Evidence: .sisyphus/evidence/task-9-perfect-alignment.json

  Scenario: Partial alignment with ASR errors
    Tool: Bash
    Preconditions: syncer package installed
    Steps:
      1. Create test data: asr has 'helo' (misspelled) and 'world', lyrics has 'hello world'
      2. Run snap_words_to_lyrics(asr_words, lyrics)
      3. Verify: 'hello' gets timestamp via fuzzy match (Levenshtein ratio > 0.7), 'world' exact match
    Expected Result: Both words get timestamps, 'hello' confidence slightly lower
    Failure Indicators: 'hello' unmatched, exception on mismatch
    Evidence: .sisyphus/evidence/task-9-partial-alignment.json

  Scenario: Empty ASR output
    Tool: Bash
    Preconditions: syncer package installed
    Steps:
      1. Run snap_words_to_lyrics([], ['hello world'])
      2. Verify: returns 1 line, words have timestamp 0, overall confidence = 0
    Expected Result: Graceful degradation, no crash, confidence 0
    Failure Indicators: Exception, crash, non-zero confidence
    Evidence: .sisyphus/evidence/task-9-empty-asr.json
  ```

  **Commit**: YES (groups with Tasks 7, 8)
  - Message: `feat(alignment): Demucs, WhisperX, and snap-to-lyrics modules`
  - Files: `src/syncer/alignment/snap.py, tests/test_snap.py`
  - Pre-commit: `pytest tests/test_snap.py`

---

- [x] 10. Sync Pipeline Orchestrator

  **What to do**:
  - Create `src/syncer/pipeline.py` — the main orchestration module:
    - Class `SyncPipeline`:
      - `__init__(self, settings: Settings)` — initializes all sub-modules:
        - `VocalSeparator` (from Task 7)
        - `WordAligner` (from Task 8)
        - `LrcLibClient` (from Task 3)
        - `SpotifyClient` (from Task 4, optional)
        - `YouTubeExtractor` (from Task 5)
        - `CacheManager` (from Task 6)
      - `sync(self, request: SyncRequest) -> SyncResult`:
        - **Step 1: Resolve input** — determine what we have:
          - If `request.url` contains 'spotify.com' → resolve via Spotify client for metadata (title, artist, ISRC, duration)
          - If `request.url` contains 'youtube.com' or 'youtu.be' → extract YouTube ID, use yt-dlp for metadata
          - If `request.title`/`request.artist` provided → use directly
        - **Step 2: Check cache** — `cache.get_cached(title, artist, duration)`. If hit, return immediately.
        - **Step 3: Fetch lyrics** — `lrclib.fetch_lyrics(title, artist, duration)`
          - If LRCLIB returns `syncedLyrics` → parse LRC, set `timing_source='lrclib_synced'`
          - If LRCLIB returns only `plainLyrics` → use as lyrics text, proceed to alignment
          - If LRCLIB returns nothing → proceed to alignment (will use WhisperX transcription as lyrics)
        - **Step 4: Audio extraction** (only if word-level enhancement or full alignment needed):
          - If input is YouTube URL → `youtube.extract_audio(url, temp_dir)`
          - If input is Spotify URL → search YouTube for `"{title} {artist}"` using yt-dlp search, download first result
          - If input is title/artist query → search YouTube using yt-dlp search
        - **Step 5: Vocal isolation** — `demucs.separate(audio_path, temp_dir)`
        - **Step 6: Word alignment** — `aligner.align(vocals_path)`
        - **Step 7: Snap to lyrics** — if lyrics text available:
          - `snap_words_to_lyrics(asr_words, lyrics_lines)` → `SyncedLine[]` with word timestamps
          - Set `timing_source='lrclib_enhanced'` (had LRC) or `'whisperx_aligned'` (had plain text)
        - **Step 7b: No lyrics text** — if no lyrics from LRCLIB:
          - Use WhisperX transcription as both lyrics and timestamps
          - Set `timing_source='whisperx_only'`
        - **Step 8: Score confidence** — compute overall confidence
        - **Step 9: Cache result** — `cache.store_result(result)`
        - **Step 10: Cleanup** — `tempfile.TemporaryDirectory` auto-cleans, but verify
    - **Error handling at each step**:
      - Spotify fails → log warning, continue without ISRC
      - LRCLIB fails → log warning, proceed to full alignment
      - yt-dlp fails → return error: "Could not download audio"
      - Demucs fails → return error: "Vocal separation failed"
      - WhisperX fails → return error: "Alignment failed"
      - Snap fails → return WhisperX-only result with lower confidence
    - **YouTube search for non-YouTube inputs**: use `yt_dlp.YoutubeDL({'default_search': 'ytsearch1'}).extract_info(f'ytsearch1:{title} {artist}', download=False)` to find YouTube URL
  - Write integration tests in `tests/test_pipeline.py`: test with mocked sub-modules + one real end-to-end test

  **Must NOT do**:
  - Do NOT implement retry logic — if a step fails, return error or degraded result
  - Do NOT implement parallel processing of multiple steps
  - Do NOT add WebSocket or streaming progress updates
  - Do NOT handle more than one song per request

  **Recommended Agent Profile**:
  - **Category**: `deep`
    - Reason: This is the integration hub connecting 6 modules. Error handling across the pipeline is the key challenge. Needs careful orchestration logic.
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (integration task)
  - **Parallel Group**: Wave 3 (first, then Tasks 11+12 parallel)
  - **Blocks**: Tasks 11, 12, 13
  - **Blocked By**: Tasks 3, 4, 5, 6, 7, 8, 9

  **References**:

  **Pattern References**:
  - All modules from Tasks 3-9 are inputs to this orchestrator
  - yt-dlp search: `ytsearch1:query` format searches YouTube and returns first result

  **API/Type References**:
  - `SyncRequest(url=..., title=..., artist=...)` — input model from Task 2
  - `SyncResult(track=..., lines=..., confidence=..., timing_source=...)` — output model from Task 2
  - `tempfile.TemporaryDirectory()` as context manager for all temp files

  **WHY Each Reference Matters**:
  - The yt-dlp search feature is how we handle Spotify URLs and title/artist queries — search YouTube for audio since Spotify provides none
  - `tempfile.TemporaryDirectory` ensures cleanup even if pipeline crashes mid-way

  **Acceptance Criteria**:
  - [ ] Full pipeline works: YouTube URL → SyncResult with lines and words
  - [ ] Cache path works: second identical request returns cached result
  - [ ] Degraded path works: LRCLIB fails → still produces result via WhisperX
  - [ ] Error path works: invalid URL → returns clear error (not crash)
  - [ ] Temp files cleaned up after pipeline completes
  - [ ] `pytest tests/test_pipeline.py` passes

  **QA Scenarios (MANDATORY):**
  ```
  Scenario: Full pipeline — YouTube URL to synced lyrics
    Tool: Bash
    Preconditions: All models loaded, network available
    Steps:
      1. Create SyncPipeline with default settings
      2. Call sync(SyncRequest(url='https://www.youtube.com/watch?v=dQw4w9WgXcQ'))
      3. Verify result: track.title is non-empty, lines has >5 entries, words exist in lines, confidence > 0
      4. Verify timing_source is one of the 4 valid values
    Expected Result: Valid SyncResult with populated lines, words, and confidence
    Failure Indicators: Exception, empty lines, confidence=0, missing track info
    Evidence: .sisyphus/evidence/task-10-full-pipeline.json

  Scenario: Cache hit returns fast
    Tool: Bash
    Preconditions: First pipeline run completed and cached
    Steps:
      1. Call sync() with same URL again
      2. Measure time — should be <500ms
      3. Verify result.cached == True
    Expected Result: Fast return, cached=True, same data as first run
    Failure Indicators: Slow return (>1s), cached=False, different data
    Evidence: .sisyphus/evidence/task-10-cache-hit.txt

  Scenario: Invalid URL returns clear error
    Tool: Bash
    Preconditions: Pipeline initialized
    Steps:
      1. Call sync(SyncRequest(url='https://example.com/notavideo'))
      2. Verify: returns error with descriptive message, no unhandled exception
    Expected Result: Error response with message like 'Could not download audio'
    Failure Indicators: Unhandled exception, generic error, process crash
    Evidence: .sisyphus/evidence/task-10-invalid-url.txt
  ```

  **Commit**: YES
  - Message: `feat(pipeline): sync pipeline orchestrator`
  - Files: `src/syncer/pipeline.py, tests/test_pipeline.py`
  - Pre-commit: `pytest tests/test_pipeline.py -k 'not e2e'`

---

- [ ] 11. FastAPI REST API

  **What to do**:
  - Create `src/syncer/api.py`:
    - FastAPI app with:
      ```python
      app = FastAPI(title="Syncer", version="0.1.0")
      
      # Global pipeline instance (models loaded once at startup)
      pipeline: SyncPipeline | None = None
      
      @app.on_event("startup")
      async def startup():
          global pipeline
          pipeline = SyncPipeline(Settings())
      
      @app.post("/api/sync")
      async def sync_lyrics(request: SyncRequest) -> SyncResult:
          result = pipeline.sync(request)
          return result
      
      @app.get("/api/cache/{track_id}")
      async def get_cached(track_id: str) -> SyncResult:
          result = pipeline.cache.get_by_id(track_id)
          if not result:
              raise HTTPException(404, "Track not found in cache")
          return result
      
      @app.get("/health")
      async def health():
          return {"status": "ok", "models_loaded": pipeline is not None}
      ```
    - The sync endpoint is **synchronous** (runs pipeline inline) — client blocks until done
    - No authentication, no rate limiting, no CORS (local dev only)
    - Add `processing_time_seconds` to response by timing the pipeline call
    - Error handling: pipeline errors → HTTP 500 with `{"detail": "error message"}`
    - Set generous timeout: the pipeline may take 60-120s on CPU
  - Write tests in `tests/test_api.py`: use FastAPI TestClient with mocked pipeline

  **Must NOT do**:
  - Do NOT add authentication or API keys
  - Do NOT add rate limiting or request queuing
  - Do NOT add CORS headers (local dev, no browser frontend)
  - Do NOT add WebSocket endpoints
  - Do NOT create OpenAPI description decorators on internal functions

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: FastAPI setup with ML model lifecycle (startup loading). Test client mocking. Moderate complexity.
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Task 12)
  - **Parallel Group**: Wave 3 (after Task 10, parallel with Task 12)
  - **Blocks**: Task 13
  - **Blocked By**: Tasks 6, 10

  **References**:

  **API/Type References**:
  - `SyncRequest` and `SyncResult` from Task 2 models — FastAPI auto-generates OpenAPI from these
  - `SyncPipeline.sync(request)` from Task 10

  **External References**:
  - FastAPI startup events: https://fastapi.tiangolo.com/advanced/events/
  - FastAPI TestClient: https://fastapi.tiangolo.com/tutorial/testing/

  **WHY Each Reference Matters**:
  - Startup event ensures models are loaded once, not per-request (10-30s savings)
  - TestClient allows testing without starting a server or loading real ML models

  **Acceptance Criteria**:
  - [ ] `uvicorn syncer.api:app --port 8000` starts without error
  - [ ] `curl http://localhost:8000/health` returns `{"status": "ok"}`
  - [ ] `POST /api/sync` with valid request returns SyncResult JSON
  - [ ] `GET /api/cache/{id}` returns 404 for unknown tracks
  - [ ] `pytest tests/test_api.py` passes

  **QA Scenarios (MANDATORY):**
  ```
  Scenario: API health check and sync endpoint
    Tool: Bash
    Preconditions: API server running on port 8000
    Steps:
      1. curl -s http://localhost:8000/health | python -c "import json,sys; d=json.load(sys.stdin); assert d['status']=='ok'; print('Health OK')"
      2. curl -s -X POST http://localhost:8000/api/sync -H 'Content-Type: application/json' -d '{"title":"Yesterday","artist":"The Beatles"}' | python -c "import json,sys; d=json.load(sys.stdin); assert 'lines' in d; assert len(d['lines'])>0; print('Sync OK:', len(d['lines']), 'lines')"
    Expected Result: Health returns ok, sync returns valid JSON with lines
    Failure Indicators: Connection refused, 500 error, empty response
    Evidence: .sisyphus/evidence/task-11-api-endpoints.txt

  Scenario: API error handling
    Tool: Bash
    Preconditions: API server running
    Steps:
      1. curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/api/cache/nonexistent — expect 404
      2. curl -s -X POST http://localhost:8000/api/sync -H 'Content-Type: application/json' -d '{}' — expect 422 (validation error, no url or title)
    Expected Result: 404 for missing cache, 422 for invalid request
    Failure Indicators: 500 error, crash, no response
    Evidence: .sisyphus/evidence/task-11-api-errors.txt
  ```

  **Commit**: YES (groups with Task 12)
  - Message: `feat(interfaces): FastAPI API and CLI`
  - Files: `src/syncer/api.py, tests/test_api.py`
  - Pre-commit: `pytest tests/test_api.py`

---

- [ ] 12. CLI Interface

  **What to do**:
  - Create `src/syncer/__main__.py`:
    - Entry point: `python -m syncer <url_or_query> [--verbose]`
    - Parse arguments:
      - Positional: URL (YouTube/Spotify) or title/artist query string
      - `--verbose` / `-v`: enable DEBUG logging
      - `--format json`: (default and only option for MVP, but arg exists for future)
    - Detect input type:
      - Contains 'youtube.com' or 'youtu.be' or 'spotify.com' → treat as URL
      - Otherwise → treat as title/artist search query (pass to LRCLIB as title, try to split on ' - ' for artist)
    - Initialize `SyncPipeline`, call `pipeline.sync(request)`, print `result.model_dump_json(indent=2)` to stdout
    - Log pipeline progress to stderr (so stdout is clean JSON for piping)
    - Handle Ctrl+C gracefully (cleanup temp files)
    - Use `argparse` (stdlib) — no Click or Typer dependency for MVP
  - Write tests in `tests/test_cli.py`: test argument parsing, input type detection

  **Must NOT do**:
  - Do NOT add progress bars or rich terminal output
  - Do NOT add interactive mode
  - Do NOT add config file loading
  - Do NOT add multiple output formats (JSON only)
  - Do NOT use Click or Typer

  **Recommended Agent Profile**:
  - **Category**: `quick`
    - Reason: Simple argparse wrapper around the pipeline. Straightforward.
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES (with Task 11)
  - **Parallel Group**: Wave 3 (after Task 10, parallel with Task 11)
  - **Blocks**: Task 13
  - **Blocked By**: Task 10

  **References**:

  **API/Type References**:
  - `SyncPipeline.sync(SyncRequest(...))` → `SyncResult`
  - `SyncResult.model_dump_json(indent=2)` for pretty JSON output

  **External References**:
  - Python argparse: https://docs.python.org/3/library/argparse.html

  **WHY Each Reference Matters**:
  - `model_dump_json` handles all serialization correctly including None fields and nested models
  - Logging to stderr keeps stdout clean for JSON piping (`python -m syncer ... | jq .`)

  **Acceptance Criteria**:
  - [ ] `python -m syncer "Yesterday Beatles"` outputs valid JSON to stdout
  - [ ] `python -m syncer --help` shows usage information
  - [ ] `python -m syncer "Yesterday Beatles" | jq '.lines | length'` returns a number >0
  - [ ] `pytest tests/test_cli.py` passes

  **QA Scenarios (MANDATORY):**
  ```
  Scenario: CLI produces valid JSON output
    Tool: Bash
    Preconditions: syncer package installed, models available
    Steps:
      1. Run `python -m syncer "Yesterday Beatles" 2>/dev/null | python -c "import json,sys; d=json.load(sys.stdin); print('Lines:', len(d['lines']), 'Confidence:', d['confidence'])"` 
      2. Verify: output is valid JSON, has lines, has confidence
    Expected Result: Valid JSON with >0 lines and confidence between 0-1
    Failure Indicators: JSON parse error, empty output, non-JSON on stdout
    Evidence: .sisyphus/evidence/task-12-cli-output.json

  Scenario: CLI handles invalid input gracefully
    Tool: Bash
    Preconditions: syncer package installed
    Steps:
      1. Run `python -m syncer "" 2>&1; echo "Exit: $?"` — empty input
      2. Verify: non-zero exit code, error message on stderr
    Expected Result: Error message, non-zero exit code, no crash
    Failure Indicators: Zero exit code on error, crash, unhandled exception traceback
    Evidence: .sisyphus/evidence/task-12-cli-error.txt
  ```

  **Commit**: YES (groups with Task 11)
  - Message: `feat(interfaces): FastAPI API and CLI`
  - Files: `src/syncer/__main__.py, tests/test_cli.py`
  - Pre-commit: `pytest tests/test_cli.py`

---

- [ ] 13. End-to-End Tests with 5 Reference Songs

  **What to do**:
  - Create `tests/test_e2e.py` with comprehensive end-to-end tests:
    - **Test setup**: Initialize SyncPipeline once for entire test module (expensive — use `@pytest.fixture(scope='module')`)
    - **5 reference song tests** (each is a separate test function):
      1. `test_yesterday_beatles()`: Simple song, should produce high confidence
         - Query: `SyncRequest(title="Yesterday", artist="The Beatles")`
         - Assert: >5 lines, >20 words total, confidence >0.3
      2. `test_shake_it_off_taylor_swift()`: Modern pop, good LRCLIB coverage
         - Query: `SyncRequest(title="Shake It Off", artist="Taylor Swift")`
         - Assert: >10 lines, words exist, confidence >0.2
      3. `test_never_gonna_give_you_up()`: Known YouTube URL test
         - Query: `SyncRequest(url="https://www.youtube.com/watch?v=dQw4w9WgXcQ")`
         - Assert: valid result with lines and words
      4. `test_lose_yourself_eminem()`: Rap stress test
         - Query: `SyncRequest(title="Lose Yourself", artist="Eminem")`
         - Assert: produces output (may have lower confidence, that's OK)
      5. `test_bohemian_rhapsody_queen()`: Complex structure
         - Query: `SyncRequest(title="Bohemian Rhapsody", artist="Queen")`
         - Assert: >20 lines (long song), confidence >0.1
    - **Cache test**: Run one song twice, verify second is fast + cached=True
    - **API test**: Start TestClient, POST to /api/sync, verify response structure
    - **Error test**: Invalid URL returns error, not crash
    - Create `tests/conftest.py` with shared fixtures:
      - `pipeline` fixture (module-scoped)
      - `test_client` fixture (FastAPI TestClient)
  - Mark long-running tests with `@pytest.mark.slow` decorator for optional skipping

  **Must NOT do**:
  - Do NOT test timing accuracy in milliseconds — just test that output is structurally valid
  - Do NOT create test audio fixtures (use real songs via network)
  - Do NOT mock the pipeline in e2e tests — the point is to test the real thing

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
    - Reason: Integration testing with real ML models and network. Tests may be slow (minutes). Needs patience and good fixture management.
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 4 (solo, depends on everything)
  - **Blocks**: F1-F4
  - **Blocked By**: Tasks 11, 12

  **References**:

  **Pattern References**:
  - All previous task modules are exercised here
  - FastAPI TestClient: `from fastapi.testclient import TestClient; client = TestClient(app)`

  **API/Type References**:
  - `SyncResult` model: verify `.lines`, `.confidence`, `.timing_source`, `.track` fields
  - pytest markers: `@pytest.mark.slow` for tests that take >30s

  **Acceptance Criteria**:
  - [ ] All 5 reference songs produce valid, non-empty SyncResult
  - [ ] Cache test shows second request is <500ms and has cached=True
  - [ ] API endpoint test returns valid JSON response
  - [ ] Error test returns error without crashing
  - [ ] `pytest tests/test_e2e.py -v` shows results for all tests

  **QA Scenarios (MANDATORY):**
  ```
  Scenario: Run full test suite
    Tool: Bash
    Preconditions: All modules built, models available, network available
    Steps:
      1. Run `pytest tests/test_e2e.py -v --tb=short 2>&1 | tee .sisyphus/evidence/task-13-test-results.txt`
      2. Count PASSED vs FAILED
      3. Verify: ≥4 of 5 songs pass, cache test passes, API test passes
    Expected Result: ≥4/5 songs pass, cache works, API works. Some songs may have lower confidence but still produce output.
    Failure Indicators: <3 songs pass, cache fails, API crash, import errors
    Evidence: .sisyphus/evidence/task-13-test-results.txt

  Scenario: Individual song output inspection
    Tool: Bash
    Preconditions: test suite has run
    Steps:
      1. Run `python -m syncer "Yesterday Beatles" 2>/dev/null | python -c "import json,sys; d=json.load(sys.stdin); print(f'Lines: {len(d[chr(108)+chr(105)+chr(110)+chr(101)+chr(115)])}, Words: {sum(len(l[chr(119)+chr(111)+chr(114)+chr(100)+chr(115)]) for l in d[chr(108)+chr(105)+chr(110)+chr(101)+chr(115)])}, Confidence: {d[chr(99)+chr(111)+chr(110)+chr(102)+chr(105)+chr(100)+chr(101)+chr(110)+chr(99)+chr(101)]:.2f}, Source: {d[chr(116)+chr(105)+chr(109)+chr(105)+chr(110)+chr(103)+chr(95)+chr(115)+chr(111)+chr(117)+chr(114)+chr(99)+chr(101)]}')"` 
    Expected Result: Structured summary showing lines, word count, confidence, and timing source
    Evidence: .sisyphus/evidence/task-13-yesterday-output.json
  ```

  **Commit**: YES
  - Message: `test: end-to-end tests with 5 reference songs`
  - Files: `tests/test_e2e.py, tests/conftest.py`
  - Pre-commit: `pytest tests/test_e2e.py -v --tb=short`

---

## Final Verification Wave (MANDATORY — after ALL implementation tasks)

> 4 review agents run in PARALLEL. ALL must APPROVE. Rejection → fix → re-run.

- [ ] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists (read file, curl endpoint, run command). For each "Must NOT Have": search codebase for forbidden patterns — reject with file:line if found. Check evidence files exist in .sisyphus/evidence/. Compare deliverables against plan. Verify all 5 reference songs produce valid output.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [ ] F2. **Code Quality Review** — `unspecified-high`
  Run `python -m py_compile` on all .py files + `pytest --tb=short`. Review all files for: `# type: ignore`, empty except blocks, hardcoded secrets, print statements in prod code, unused imports. Check AI slop: abstract base classes, "plugin" patterns, excessive comments, over-abstraction, >2 levels of nesting.
  Output: `Build [PASS/FAIL] | Tests [N pass/N fail] | Files [N clean/N issues] | VERDICT`

- [ ] F3. **Real QA with Reference Songs** — `unspecified-high`
  Start the API server. Run the CLI and API against all 5 reference songs. Verify: JSON output is valid, `lines` array is non-empty, each line has `start`/`end`, words array exists, confidence score is between 0-1. Test cache: second request returns in <500ms. Test error cases: invalid URL, non-music video, empty query. Save all outputs to `.sisyphus/evidence/final-qa/`.
  Output: `Songs [N/5 pass] | Cache [PASS/FAIL] | Errors [N/N handled] | VERDICT`

- [ ] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual code. Verify 1:1 — everything in spec was built (no missing), nothing beyond spec was built (no creep). Check "Must NOT do" compliance: no abstract base classes, no job queue, no Docker, no plugin system, no auth/rate limiting. Flag unaccounted changes.
  Output: `Tasks [N/N compliant] | Guardrails [N/N respected] | Unaccounted [CLEAN/N files] | VERDICT`

---

## Commit Strategy

| After Task(s) | Commit Message | Files |
|---------------|----------------|-------|
| 1 | `feat(init): project scaffolding with ML smoke test` | pyproject.toml, src/syncer/__init__.py, smoke_test.py |
| 2 | `feat(models): add Pydantic data models and config` | models.py, config.py |
| 3-6 (group) | `feat(clients): LRCLIB, Spotify, YouTube, and cache modules` | clients/*.py, cache.py |
| 7-9 (group) | `feat(alignment): Demucs, WhisperX, and snap-to-lyrics modules` | alignment/*.py |
| 10 | `feat(pipeline): sync pipeline orchestrator` | pipeline.py |
| 11-12 (group) | `feat(interfaces): FastAPI API and CLI` | api.py, main.py |
| 13 | `test: end-to-end tests with 5 reference songs` | tests/*.py |

---

## Success Criteria

### Verification Commands
```bash
# Install and import check
python -c "import syncer; print(syncer.__version__)"  # Expected: 0.1.0

# CLI end-to-end
python -m syncer "Never Gonna Give You Up Rick Astley" | python -c "import json,sys; d=json.load(sys.stdin); assert 'lines' in d and len(d['lines'])>0"

# API start + request
uvicorn syncer.api:app --port 8000 &
sleep 2
curl -s -X POST http://localhost:8000/api/sync -H "Content-Type: application/json" -d '{"query":"Yesterday Beatles"}' | python -c "import json,sys; d=json.load(sys.stdin); assert d['confidence']>0"

# Cache test (second request fast)
time curl -s -X POST http://localhost:8000/api/sync -H "Content-Type: application/json" -d '{"query":"Yesterday Beatles"}'
# Expected: <500ms response time

# Test suite
pytest -v  # Expected: ≥80% pass rate

# Reference songs
for song in "Never Gonna Give You Up Rick Astley" "Shake It Off Taylor Swift" "Lose Yourself Eminem" "Yesterday Beatles" "Bohemian Rhapsody Queen"; do
  python -m syncer "$song" > /dev/null && echo "PASS: $song" || echo "FAIL: $song"
done
# Expected: 5/5 produce output (quality varies)
```

### Final Checklist
- [ ] All "Must Have" features present and working
- [ ] All "Must NOT Have" guardrails respected
- [ ] All 5 reference songs produce valid JSON output
- [ ] pytest passes with ≥80% green
- [ ] Cached results return in <500ms
- [ ] API and CLI both functional
