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
