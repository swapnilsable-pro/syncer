"""FastAPI REST API for the Syncer lyrics synchronization service."""

import logging
import warnings
from contextlib import asynccontextmanager
from pathlib import Path

# Suppress noisy torchcodec/pyannote warnings (not used in our pipeline)
warnings.filterwarnings("ignore", message=".*torchcodec is not installed correctly.*")
warnings.filterwarnings("ignore", message=".*Lightning automatically upgraded.*")

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from syncer.config import Settings
from syncer.models import SyncRequest, SyncResult, TrackSummary
from syncer.pipeline import SyncPipeline

logger = logging.getLogger(__name__)

# Global pipeline instance (loaded once at startup)
_pipeline: SyncPipeline | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pipeline
    settings = Settings()
    _pipeline = SyncPipeline(settings)
    logger.info("Pipeline initialized")
    yield
    _pipeline = None


app = FastAPI(title="Syncer", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok", "models_loaded": _pipeline is not None}


@app.post("/api/sync")
async def sync_lyrics(request: SyncRequest) -> SyncResult:
    if _pipeline is None:
        raise HTTPException(503, "Pipeline not initialized")
    try:
        result = _pipeline.sync(request)
        return result
    except ValueError as e:
        raise HTTPException(422, str(e))
    except RuntimeError as e:
        raise HTTPException(500, str(e))


@app.post("/api/retry/{track_id}")
async def retry_track(track_id: str) -> SyncResult:
    if _pipeline is None:
        raise HTTPException(503, "Pipeline not initialized")
    track = _pipeline.cache.get_track_info(track_id)
    if track is None:
        raise HTTPException(404, "Track not found in cache")

    url: str | None = None
    if track["youtube_id"]:
        url = f"https://www.youtube.com/watch?v={track['youtube_id']}"

    request = SyncRequest(
        url=url,
        title=track["title"],
        artist=track["artist"],
        force=True,
    )
    try:
        return _pipeline.sync(request)
    except ValueError as e:
        raise HTTPException(422, str(e))
    except RuntimeError as e:
        raise HTTPException(500, str(e))


@app.get("/api/cache/{track_id}")
async def get_cached(track_id: str) -> SyncResult:
    if _pipeline is None:
        raise HTTPException(503, "Pipeline not initialized")
    result = _pipeline.cache.get_by_id(track_id)
    if result is None:
        raise HTTPException(404, "Track not found in cache")
    return result


@app.get("/api/tracks")
async def list_tracks() -> list[TrackSummary]:
    if _pipeline is None:
        raise HTTPException(503, "Pipeline not initialized")
    return _pipeline.cache.list_tracks()


# Serve frontend
_static_dir = Path(__file__).parent / "static"


@app.get("/")
async def index():
    return FileResponse(_static_dir / "index.html")


app.mount("/static", StaticFiles(directory=_static_dir), name="static")
