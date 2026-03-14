import hashlib
import logging
import sqlite3
from pathlib import Path

from syncer.models import SyncResult, TrackSummary

logger = logging.getLogger(__name__)

CREATE_TRACKS = """
CREATE TABLE IF NOT EXISTS tracks (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    artist TEXT NOT NULL,
    duration REAL,
    isrc TEXT,
    spotify_id TEXT,
    youtube_id TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_SYNC_RESULTS = """
CREATE TABLE IF NOT EXISTS sync_results (
    track_id TEXT PRIMARY KEY REFERENCES tracks(id),
    result_json TEXT NOT NULL,
    confidence REAL,
    timing_source TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


def generate_track_id(title: str, artist: str, duration: float | None, language: str | None = None) -> str:
    """Generate a deterministic track ID from title, artist, duration, and optional language."""
    key = f"{title.lower().strip()}|{artist.lower().strip()}|{round(duration or 0)}|{language or 'auto'}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


class CacheManager:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(CREATE_TRACKS)
            conn.execute(CREATE_SYNC_RESULTS)
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def get_cached(
        self, title: str, artist: str, duration: float | None = None, language: str | None = None
    ) -> SyncResult | None:
        """Look up cached result. Returns None on miss."""
        track_id = generate_track_id(title, artist, duration, language=language)
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT result_json FROM sync_results WHERE track_id = ?",
                    (track_id,),
                ).fetchone()
                if row:
                    result = SyncResult.model_validate_json(row[0])
                    result.cached = True
                    return result
        except Exception:
            logger.exception("Cache read failed for %s - %s", title, artist)
        return None

    def get_by_id(self, track_id: str) -> SyncResult | None:
        """Look up cached result by track_id directly."""
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT result_json FROM sync_results WHERE track_id = ?",
                    (track_id,),
                ).fetchone()
                if row:
                    result = SyncResult.model_validate_json(row[0])
                    result.cached = True
                    return result
        except Exception:
            logger.exception("Cache read by ID failed for %s", track_id)
        return None

    def store_result(self, result: SyncResult, language: str | None = None) -> None:
        """Store SyncResult in cache. Overwrites existing entry."""
        track_id = generate_track_id(
            result.track.title,
            result.track.artist,
            result.track.duration,
            language=language,
        )
        try:
            with self._connect() as conn:
                conn.execute(
                    """INSERT OR REPLACE INTO tracks (id, title, artist, duration, isrc, spotify_id, youtube_id)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (
                        track_id,
                        result.track.title,
                        result.track.artist,
                        result.track.duration,
                        result.track.isrc,
                        result.track.spotify_id,
                        result.track.youtube_id,
                    ),
                )
                conn.execute(
                    """INSERT OR REPLACE INTO sync_results (track_id, result_json, confidence, timing_source, updated_at)
                       VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)""",
                    (
                        track_id,
                        result.model_dump_json(),
                        result.confidence,
                        result.timing_source,
                    ),
                )
                conn.commit()
        except Exception:
            logger.exception(
                "Cache write failed for %s - %s",
                result.track.title,
                result.track.artist,
            )

    def list_tracks(self) -> list[TrackSummary]:
        """Return all cached tracks with summary metadata, newest first."""
        try:
            with self._connect() as conn:
                rows = conn.execute(
                    """SELECT t.id, t.title, t.artist, t.duration,
                              sr.confidence, sr.timing_source, sr.created_at
                       FROM tracks t
                       LEFT JOIN sync_results sr ON t.id = sr.track_id
                       ORDER BY sr.created_at DESC"""
                ).fetchall()
                return [
                    TrackSummary(
                        track_id=row[0],
                        title=row[1],
                        artist=row[2],
                        duration=row[3] or 0.0,
                        confidence=row[4],
                        timing_source=row[5],
                        created_at=row[6],
                    )
                    for row in rows
                ]
        except Exception:
            logger.exception("Failed to list tracks")
            return []

    def get_track_info(self, track_id: str) -> dict | None:
        """Look up stored track metadata by track_id. Returns dict with title, artist, youtube_id, spotify_id, or None."""
        try:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT title, artist, duration, spotify_id, youtube_id FROM tracks WHERE id = ?",
                    (track_id,),
                ).fetchone()
                if row:
                    return {
                        "title": row[0],
                        "artist": row[1],
                        "duration": row[2],
                        "spotify_id": row[3],
                        "youtube_id": row[4],
                    }
        except Exception:
            logger.exception("Track info lookup failed for %s", track_id)
        return None

    def clear_all(self) -> int:
        """Delete all cached entries. Returns number of entries cleared."""
        try:
            with self._connect() as conn:
                count = conn.execute("SELECT COUNT(*) FROM sync_results").fetchone()[0]
                conn.execute("DELETE FROM sync_results")
                conn.execute("DELETE FROM tracks")
                conn.commit()
                logger.info("Cache cleared: %d entries removed", count)
                return count
        except Exception:
            logger.exception("Cache clear failed")
            return 0
