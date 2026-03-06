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

# Task 2: Data Models + Pydantic Schemas + Config

## Pydantic v2 Key Differences
- Use `model_dump_json()` instead of `.json()` for serialization
- Use `model_validate_json()` instead of `.parse_raw()` for deserialization
- `model_dump()` returns dict (replaces `.dict()`)
- Union types use `|` syntax (Python 3.10+): `str | None` instead of `Optional[str]`

## Settings with pydantic-settings
- `BaseSettings` from `pydantic_settings` (separate package)
- `SettingsConfigDict` with `env_prefix="SYNCER_"` means env vars like `SYNCER_WHISPERX_MODEL` override field `whisperx_model`
- `env_file=".env"` loads from .env file (if present)
- `extra="ignore"` silently ignores unknown env vars
- Path fields work natively: `Path = Path.home() / ".syncer"` is valid

## Model Design Decisions
- Kept models simple: no validators, no computed fields, no inheritance
- `SyncedWord` has confidence (0.0-1.0) for word-level confidence
- `SyncResult` has overall confidence + timing_source to track sync quality
- `SyncRequest` allows flexible input: url OR title+artist OR nothing (all optional)
- Optional fields use `| None = None` pattern consistently

## Test Coverage
- 17 tests total: all passing
- Covers: model creation, field validation, JSON roundtrip, Settings defaults, env override
- JSON roundtrip test verifies nested objects serialize/deserialize correctly
- Settings tests verify env_prefix works and defaults are correct

## Task 4: Spotify Metadata Client

### Spotify API URL Patterns
- **HTTPS URL format**: `https://open.spotify.com/track/{TRACK_ID}` (with optional query params like `?si=...`)
- **URI format**: `spotify:track:{TRACK_ID}`
- Both formats extract the same 22-character alphanumeric track ID
- Query parameters are safely ignored by regex matching

### Token Management
- Spotify uses OAuth2 client credentials flow for server-to-server auth
- Token endpoint: `https://accounts.spotify.com/api/token`
- Credentials sent as Base64-encoded `client_id:client_secret` in Authorization header
- Tokens expire (typically 3600s); cache with 60s buffer for safety
- Simple dict-based cache sufficient for MVP (no threading needed)

### Track Metadata API
- Endpoint: `https://api.spotify.com/v1/tracks/{TRACK_ID}`
- Returns: name, artists[], duration_ms, external_ids.isrc
- ISRC field may be missing (external_ids can be empty dict)
- Multiple artists joined with ", " separator
- Duration in milliseconds; convert to seconds for TrackInfo

### Error Handling
- 401 Unauthorized: Invalid credentials (graceful return None)
- Timeout/RequestError: Network issues (graceful return None)
- Empty credentials: Skip HTTP call entirely (return None early)
- All failures are non-fatal; client returns None instead of raising

### Testing Strategy
- Mock httpx.Client entirely to avoid network calls
- Clear token cache in setUp() to prevent test pollution
- Test both happy path and error cases
- Verify no HTTP calls made when credentials empty

# Task 3: LRCLIB Client + LRC Parser

## LRCLIB API Behavior
- Base URL: `https://lrclib.net/api`
- GET `/api/get?track_name=X&artist_name=Y&duration=Z` — exact match (preferred)
- GET `/api/search?track_name=X&artist_name=Y` — fuzzy search fallback
- Duration matching: within ±2 seconds
- Response fields: `{id, trackName, artistName, albumName, duration, instrumental, plainLyrics, syncedLyrics}`
- Instrumental tracks return `instrumental: true` with no lyrics

## LRC Format Parsing
- Timestamp format: `[MM:SS.CC]` or `[MM:SS.CCC]` (centiseconds or milliseconds)
- Metadata tags: `[ti:title]`, `[ar:artist]`, `[al:album]`, `[by:creator]`, `[length:duration]`, `[offset:ms]`, `[#:comment]`, `[re:creator]`, `[ve:version]`
- Multiple timestamps per line: only first timestamp is used, all timestamps removed from text
- Lines without timestamps are skipped
- Empty text lines (only timestamps) are skipped
- Last line gets 5s default duration (no next line to reference)

## Implementation Notes
- Used `httpx.Client` (sync) with 5s timeout for MVP
- Fallback strategy: try exact match first, then search if 404
- Exception handling: catches `httpx.TimeoutException` and `httpx.RequestError`
- `SyncedLine.words` initialized as empty list (filled by alignment in later stages)
- Dataclass `LrcLibResult` used for API response (not Pydantic, simpler for this use case)

## Test Coverage
- 15 unit tests (excluding integration): all passing
- Tests cover: basic parsing, metadata skipping, empty input, milliseconds, multiple timestamps, missing timestamps, empty text
- Mocked HTTP tests: exact match, instrumental, fallback to search, timeout, request error, no search results
- Integration test marked with `@pytest.mark.integration` (skipped by default)
- Pytest marker registered in `pyproject.toml`

## Potential Improvements (Future)
- Cache responses (Redis or in-memory)
- Async version with `httpx.AsyncClient`
- Enhanced LRC parsing (word-level timing with `<00:01.00>word` format)
- Retry logic with exponential backoff

# Task 5: YouTube Audio Extractor

## yt-dlp API Patterns
- Context manager: `with yt_dlp.YoutubeDL(opts) as ydl:` — always use this pattern
- Two-step process: `extract_info(url, download=False)` for metadata, then `download([url])` for actual download
- Options dict controls behavior: `quiet=True`, `no_warnings=True` suppress output
- Format selection: `"bestaudio/best"` gets best audio quality available

## Audio Extraction
- FFmpeg postprocessor required for WAV conversion: `{"key": "FFmpegExtractAudio", "preferredcodec": "wav"}`
- Output template: `outtmpl` uses `%(ext)s` placeholder for file extension
- Downloaded file location: use `glob()` to find output file (extension may vary)
- Duration check BEFORE download: prevents wasting bandwidth on long videos

## URL Parsing
- YouTube video IDs are always 11 characters: `[A-Za-z0-9_-]{11}`
- Multiple URL formats supported: watch, youtu.be, music.youtube.com, embed, shorts
- Regex patterns must escape dots: `youtube\.com` not `youtube.com`
- Invalid URLs return None (not exception) — caller decides error handling

## Search Functionality
- Search format: `ytsearch1:query` (1 = return 1 result)
- Options: `extract_flat=True` for search (faster, no full metadata)
- Search returns entries list; first entry has `id` field
- Graceful failure: catch all exceptions, return None on any error

## Testing Strategy
- Mock `yt_dlp.YoutubeDL` class entirely to avoid network calls
- Use context manager mocking: `mock_ydl_class.return_value.__enter__.return_value = mock_ydl`
- Create temporary WAV files in test to verify file discovery logic
- Integration test marked with `@pytest.mark.integration` (skipped by default)

## Test Results
- 15 unit tests passing (1 integration test deselected)
- Coverage: URL parsing (8 tests), extraction (4 tests), search (3 tests)
- All error paths tested: invalid URL, duration exceeded, download failure, no results

# Task 6: SQLite Cache Layer

## SQLite Design Decisions
- **Two-table schema**: `tracks` (metadata) + `sync_results` (JSON + metadata)
- **Foreign key**: `sync_results.track_id` references `tracks.id` (enforces referential integrity)
- **Deterministic track ID**: SHA256 hash of `title|artist|duration` (lowercase, stripped)
  - Ensures same track always maps to same ID regardless of input casing/whitespace
  - 16-char hex prefix sufficient for collision avoidance in MVP
- **JSON storage**: Full `SyncResult` serialized as JSON in `result_json` column
  - Pydantic v2: `model_dump_json()` for serialization, `model_validate_json()` for deserialization
  - Avoids schema bloat while preserving all nested data (lines, words, confidence)

## Implementation Notes
- **INSERT OR REPLACE**: Overwrites existing entries (idempotent cache updates)
- **Context manager pattern**: `with sqlite3.connect(db_path) as conn:` auto-commits on success
- **Exception handling**: All DB operations wrapped in try-except, logged but non-fatal
- **Lazy connection**: `_connect()` method creates fresh connection per operation (no pooling needed for MVP)
- **Timestamps**: SQLite `CURRENT_TIMESTAMP` for `created_at` and `updated_at`

## Testing Strategy
- **In-memory SQLite**: `tmp_path / "test.db"` fixture for isolated test databases
- **9 test cases**: determinism, case-insensitivity, whitespace handling, round-trip, cached flag, cache miss, overwrite, get_by_id, invalid ID
- **All tests passing**: 9/9 in 0.07s

## Gotchas Avoided
- ❌ Did NOT use SQLAlchemy (stdlib sqlite3 only, as required)
- ❌ Did NOT add migration system (simple CREATE TABLE IF NOT EXISTS sufficient)
- ❌ Did NOT add full-text search or complex indexes (MVP doesn't need them)
- ❌ Did NOT use connection pooling (single-threaded MVP)
- ✅ Used `INSERT OR REPLACE` for idempotent updates
- ✅ Stored full JSON to avoid schema fragmentation
- ✅ Made track ID deterministic for reliable lookups

## Performance Characteristics
- **Lookup**: O(1) primary key lookup on `track_id`
- **Storage**: ~1-2KB per SyncResult (JSON + metadata)
- **Scalability**: SQLite suitable for ~100k tracks (MVP scope)

# Task 7: Demucs Vocal Isolation Module

## VocalSeparator Implementation
- Lazy model loading: `_load_model()` only called on first `separate()` call
- Mono-to-stereo conversion needed: `waveform.repeat(2, 1)` — htdemucs expects 2 channels
- Normalization: `(waveform - ref.mean()) / ref.std()` where `ref = waveform.mean(0)`
- `apply_model()` returns shape `(batch, sources=4, channels=2, time)` — vocals at index 3
- Memory cleanup in `finally` block: `del model, sources` + `gc.collect()` + `self._model = None`
- Output is always stereo at 44100 Hz regardless of input format

## Testing Strategy
- 13 fast unit tests with mocked model (~1s total)
- 1 slow integration test with real Demucs model (~15-30s) marked `@pytest.mark.slow`
- Synthetic audio: `torch.sin(2 * pi * 440 * t)` — no network needed
- Mock pattern: patch both `get_model` and `apply_model`, return `torch.randn(1, 4, 2, sr*duration)` as fake sources
- Test both success and error paths (FileNotFoundError, OOM, generic RuntimeError)
- Verify memory cleanup happens on both success and failure paths

# Task 8: WhisperX Word Alignment Module

## WordAligner Implementation
- Two-stage pipeline: transcribe (faster-whisper) → align (wav2vec2) for word-level timestamps
- Both models loaded eagerly in `__init__` (not lazy) — alignment model needed alongside transcription model
- `compute_type="float32"` mandatory for CPU/MPS — "float16" crashes
- `batch_size=8` for CPU (lower than default 16 to avoid memory issues)
- Memory cleanup: `gc.collect()` + `torch.cuda.empty_cache()` after alignment
- Early return on empty segments: skip `whisperx.align()` entirely when no speech detected

## AlignedWord Dataclass
- Plain `@dataclass` (not Pydantic) — simpler for this internal data structure
- `score` field defaults to 0.0 — some words from WhisperX lack this field
- `start` and `end` also default to 0.0 via `.get()` for robustness

## WhisperX API Details
- `whisperx.load_audio(str(path))` — requires string path, not Path object
- `model.transcribe(audio, batch_size=8)` returns `{"segments": [...]}`
- `whisperx.align(segments, align_model, align_metadata, audio, device)` adds word timestamps
- Word format: `{"word": str, "start": float, "end": float, "score": float}` — score may be absent

## Testing Strategy
- 12 fast unit tests with fully mocked whisperx (~0.8s total)
- 1 slow integration test on silent audio marked `@pytest.mark.slow`
- Class-level `@patch("syncer.alignment.whisperx_aligner.whisperx")` — patches the module-level import
- Helper `_setup_mocks()` method reduces test boilerplate
- Coverage: normal words, missing score, empty segments, missing segments key, multi-segment, segments without words, missing start/end, API call verification, string path acceptance

# Task 9: Snap-to-Lyrics Text Matching + Confidence Scoring

## Smith-Waterman DP Alignment
- Smith-Waterman (local alignment) better than Needleman-Wunsch (global) for this use case
  - ASR often has extra filler words (oh, yeah, uh) not in lyrics
  - Local alignment naturally skips unmatched ASR words
- Score matrix: +2 exact (case-insensitive), +1 fuzzy (Levenshtein ratio > 0.7), -1 mismatch, -1 gap
- Traceback from max score position, not from (n,m) corner

## Levenshtein Matching
- `Levenshtein.ratio()` returns 0.0-1.0; threshold of 0.7 works well for ASR errors
- Common ASR errors: dropped letters ("helo"→"hello"), merged words, substitutions
- Case-insensitive comparison essential — ASR capitalizes inconsistently

## Timestamp Interpolation
- Matched words get ASR timestamps directly (confidence = ASR score)
- Unmatched words get linearly interpolated timestamps (confidence = 0.3)
- Three interpolation cases: before first match, between matches, after last match
- Even distribution within gap works well enough for lyrics display

## Confidence Scoring
- Per-line confidence = average of word confidences
- Overall = weighted average by word count (longer lines count more)
- Typical values: perfect match ~0.9+, fuzzy ~0.85, with interpolation ~0.7, empty ASR = 0.0

## Design Decisions
- Defined `AlignedWord` dataclass locally in snap.py (whisperx_aligner.py is still a stub)
- No abstract classes, no inheritance — plain functions
- `_flatten_lyrics()` converts lines to flat word list with position metadata for DP
- Grouping back to lines after alignment preserves original line structure

## Test Coverage
- 19 tests: perfect alignment, case-insensitive, fuzzy match, threshold, empty inputs, multiline, single word, interpolation, extra ASR words, confidence variants, text/order preservation
- All tests are pure Python — no network, no ML models, runs in 0.09s

# Task 10: Sync Pipeline Orchestrator

## Pipeline Architecture
- 9-step sequential pipeline: resolve → cache check → LRCLIB → audio extract → Demucs → WhisperX → snap → build result → cache store
- `SyncPipeline.__init__` eagerly creates CacheManager, VocalSeparator, WordAligner
- `sync(request)` is the single entry point — all orchestration logic lives here
- `_resolve_input()` handles URL parsing (Spotify/YouTube) and title/artist fallback
- `_lines_from_asr()` static method builds SyncedLines from raw ASR words (no lyrics path)

## Key Design Decisions
- `tempfile.TemporaryDirectory()` as context manager wraps steps 4-7 (audio extraction through snap)
- Audio extraction failure with synced lyrics → return LRCLIB lyrics without word timestamps (graceful degradation)
- `search_youtube()` returns URL string (not AudioResult) — need `extract_audio()` after search
- `resolve_spotify_url()` takes `client_id` and `client_secret` as positional params (not from settings directly)
- Timing source tracks provenance: lrclib_synced → lrclib_enhanced (when alignment adds word timestamps)

## Cache Key Gotcha
- Cache key = SHA256(title|artist|duration) — duration=0.0 for title/artist-only requests
- After audio extraction, duration gets updated to actual value → stored result has different key than lookup
- This means title/artist requests without pre-known duration won't cache-hit on repeat calls (acceptable for MVP)
- Fix: provide duration in request, or accept first-call always misses cache for title-only queries

## Testing Strategy
- 11 tests, all with mocked sub-modules (no network, no ML models)
- Patch targets use pipeline module path (e.g., `syncer.pipeline.fetch_lyrics` not `syncer.clients.lrclib.fetch_lyrics`)
- Cache hit test uses direct CacheManager pre-population (not two pipeline calls) to avoid duration key mismatch
- Dataclass fakes (FakeAudioResult, FakeAlignedWord, FakeLrcLibResult) avoid importing real heavy dependencies

# Task 12: CLI Interface

## argparse Design
- `ArgumentParser(prog="python -m syncer")` sets the program name in help output
- Positional arguments use `add_argument("query", help="...")` (no dashes)
- Optional flags use `add_argument("--verbose", "-v", action="store_true")`
- `parser.parse_args()` automatically handles --help and exits with code 0

## Input Detection Strategy
- Check for URL patterns first: "youtube.com", "youtu.be", "spotify.com", "spotify:"
- Fall back to title/artist parsing: split on " - " (space-dash-space)
- If no " - ", treat entire query as title only
- All fields in SyncRequest are optional, so flexible input works well

## Output Design
- JSON to stdout via `result.model_dump_json(indent=2)` — allows piping to `jq`
- Logging to stderr via `logging.basicConfig(stream=sys.stderr)` — keeps stdout clean
- Logging level controlled by --verbose flag (DEBUG vs WARNING)

## Error Handling
- Empty query: print to stderr, return 1
- ValueError/RuntimeError from pipeline: print error message to stderr, return 1
- KeyboardInterrupt (Ctrl+C): print "Interrupted" to stderr, return 130 (standard Unix code)
- All exceptions caught and handled gracefully (no stack traces to user)

## Testing Strategy
- Mock entire SyncPipeline to avoid network/ML dependencies
- Use `patch("sys.argv", [...])` to simulate command-line arguments
- Use `capsys` fixture to capture stdout/stderr
- Test both happy path and error cases
- 15 tests covering: help, empty query, URL detection, title/artist split, errors, output, logging, whitespace

## Test Coverage
- URL detection: YouTube (both formats), Spotify (both formats)
- Query parsing: title/artist split, title-only, multiple dashes
- Error handling: ValueError, RuntimeError
- Output: JSON to stdout, no errors on stderr
- Logging: verbose flag, short flag
- Edge cases: whitespace stripping, empty query

## Key Gotchas Avoided
- ❌ Did NOT use Click or Typer (argparse is stdlib)
- ❌ Did NOT add interactive mode or progress bars
- ❌ Did NOT add config file loading
- ❌ Did NOT add multiple output formats (JSON only)
- ✅ Used argparse for simplicity
- ✅ Kept stdout clean for JSON piping
- ✅ Logged to stderr for debugging
- ✅ Handled all error cases gracefully
- ✅ Made URL detection robust (multiple formats)
- ✅ Made title/artist parsing flexible (optional split)

## Test Results
- 15/15 tests passing in 1.22s
- All code paths covered
- No external dependencies (mocked)
- Ready for integration with real pipeline

# Task 11: FastAPI REST API

## FastAPI Lifespan Pattern
- Use `@asynccontextmanager` + `lifespan` parameter (NOT deprecated `@app.on_event`)
- Global `_pipeline` variable initialized in lifespan, set to None on shutdown
- `models_loaded` in health check simply checks `_pipeline is not None`

## TestClient with Lifespan
- `TestClient(app)` triggers lifespan by default → would load real ML models
- Solution: `patch("syncer.api._pipeline", mock)` bypasses lifespan entirely
- `raise_server_exceptions=False` prevents TestClient from re-raising HTTPExceptions
- Creating TestClient inside `with patch(...)` block ensures mock is active for all requests

## Error Mapping
- `ValueError` → 422 (Unprocessable Entity) — invalid input
- `RuntimeError` → 500 (Internal Server Error) — pipeline failure
- Cache miss → 404 (Not Found)
- Pipeline not initialized → 503 (Service Unavailable)

## Testing Strategy
- 10 tests, all with mocked pipeline (no network, no ML models)
- Real `SyncResult` objects used (not MagicMock) for response serialization
- `_make_sync_result()` helper for clean test data construction
- Tested both happy paths and all error paths for each endpoint

# Task 13: End-to-End Tests with 5 Reference Songs

## Test Architecture
- Shared fixtures (pipeline, test_client) in conftest.py with `scope="module"` — one expensive init per module
- All 9 tests marked `@pytest.mark.slow` — deselect with `-m "not slow"` in fast CI
- pyproject.toml already registers `slow` and `integration` markers — no need to duplicate in conftest.py

## E2E Test Design
- 5 reference songs cover different genres: classic pop (Yesterday), modern pop (Shake It Off), known URL (Rick Astley), rap (Lose Yourself), complex structure (Bohemian Rhapsody)
- Cache test depends on Yesterday running first (same module, deterministic order)
- Error tests verify ValueError for empty/invalid input without needing network
- API test uses TestClient with real lifespan (loads ML models) — true end-to-end

## Key Observations
- `SyncRequest()` with all-None fields is valid Pydantic but raises ValueError in pipeline._resolve_input()
- Invalid URL (not YouTube/Spotify) raises ValueError("Unsupported URL format: ...") in _resolve_input
- TestClient(app) triggers lifespan → real SyncPipeline init — appropriate for e2e, not for unit tests

## Code Quality Review (F2) — 2026-03-07

### Build & Tests
- All 13 .py files compile clean
- 161 tests pass, 0 fail (100% green)

### Anti-pattern Scan
- Bare except: 0
- Hardcoded secrets: 0 (matches are param names/defaults)
- ABC/abstractmethod: 0
- Plugin patterns: 0
- Print in prod: 4 in __main__.py — correct for CLI (stderr errors, stdout JSON)

### Architecture Notes
- `api.py` uses modern `lifespan` context manager, not deprecated `on_event`
- `__main__.py` correctly logs to stderr, JSON to stdout
- `snap.py` DP algorithm is Smith-Waterman local alignment — correct approach
- `pipeline.py` orchestrates 9 clean steps with proper error chain
- `cache.py` uses broad except for resilience (cache failure shouldn't crash pipeline)
- No over-abstraction anywhere: concrete classes, no interfaces, no plugin system

### Minor Issue
- `snap.py` has dead code: `_interpolate_timestamp()` is defined but never called (inline interpolation used instead in `snap_words_to_lyrics`)
