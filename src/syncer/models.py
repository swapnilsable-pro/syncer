from pydantic import BaseModel


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
    timing_source: str  # 'ctc_aligned', 'lrclib_synced', 'no_lyrics'
    cached: bool = False
    detected_language: str | None = None
    processing_time_seconds: float | None = None


class SyncRequest(BaseModel):
    url: str | None = None
    title: str | None = None
    artist: str | None = None
    language: str | None = None
    force: bool = False  # Skip cache, re-process from scratch


class TrackSummary(BaseModel):
    """Lightweight track info for listing all processed songs."""
    track_id: str
    title: str
    artist: str
    duration: float
    confidence: float | None = None
    timing_source: str | None = None
    created_at: str | None = None
