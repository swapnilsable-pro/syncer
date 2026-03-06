"""FastAPI REST API for the Syncer lyrics synchronization service."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from syncer.config import Settings
from syncer.models import SyncRequest, SyncResult
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


@app.get("/api/cache/{track_id}")
async def get_cached(track_id: str) -> SyncResult:
    if _pipeline is None:
        raise HTTPException(503, "Pipeline not initialized")
    result = _pipeline.cache.get_by_id(track_id)
    if result is None:
        raise HTTPException(404, "Track not found in cache")
    return result
