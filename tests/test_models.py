import json
import os
from pathlib import Path

import pytest

from syncer.config import Settings
from syncer.models import SyncRequest, SyncResult, SyncedLine, SyncedWord, TrackInfo


class TestSyncedWord:
    def test_create_synced_word(self):
        word = SyncedWord(text="hello", start=0.0, end=1.5, confidence=0.95)
        assert word.text == "hello"
        assert word.start == 0.0
        assert word.end == 1.5
        assert word.confidence == 0.95

    def test_synced_word_all_fields(self):
        word = SyncedWord(text="world", start=2.0, end=3.5, confidence=0.87)
        assert word.model_dump() == {
            "text": "world",
            "start": 2.0,
            "end": 3.5,
            "confidence": 0.87,
        }


class TestSyncedLine:
    def test_create_synced_line(self):
        words = [
            SyncedWord(text="hello", start=0.0, end=1.5, confidence=0.95),
            SyncedWord(text="world", start=1.5, end=3.0, confidence=0.92),
        ]
        line = SyncedLine(text="hello world", start=0.0, end=3.0, words=words)
        assert line.text == "hello world"
        assert line.start == 0.0
        assert line.end == 3.0
        assert len(line.words) == 2
        assert line.words[0].text == "hello"

    def test_synced_line_empty_words(self):
        line = SyncedLine(text="test", start=0.0, end=1.0, words=[])
        assert line.words == []


class TestTrackInfo:
    def test_create_track_info_minimal(self):
        track = TrackInfo(title="Song", artist="Artist", duration=180.0)
        assert track.title == "Song"
        assert track.artist == "Artist"
        assert track.duration == 180.0
        assert track.isrc is None
        assert track.source_url is None
        assert track.spotify_id is None
        assert track.youtube_id is None

    def test_create_track_info_full(self):
        track = TrackInfo(
            title="Song",
            artist="Artist",
            duration=180.0,
            isrc="USRC12345678",
            source_url="https://example.com",
            spotify_id="spotify123",
            youtube_id="youtube123",
        )
        assert track.isrc == "USRC12345678"
        assert track.source_url == "https://example.com"
        assert track.spotify_id == "spotify123"
        assert track.youtube_id == "youtube123"


class TestSyncResult:
    def test_create_sync_result(self):
        track = TrackInfo(title="Song", artist="Artist", duration=180.0)
        words = [SyncedWord(text="hello", start=0.0, end=1.5, confidence=0.95)]
        lines = [SyncedLine(text="hello", start=0.0, end=1.5, words=words)]
        result = SyncResult(
            track=track,
            lines=lines,
            confidence=0.92,
            timing_source="lrclib_synced",
        )
        assert result.track.title == "Song"
        assert len(result.lines) == 1
        assert result.confidence == 0.92
        assert result.timing_source == "lrclib_synced"
        assert result.cached is False
        assert result.processing_time_seconds is None

    def test_sync_result_with_optional_fields(self):
        track = TrackInfo(title="Song", artist="Artist", duration=180.0)
        lines = []
        result = SyncResult(
            track=track,
            lines=lines,
            confidence=0.85,
            timing_source="whisperx_only",
            cached=True,
            processing_time_seconds=45.5,
        )
        assert result.cached is True
        assert result.processing_time_seconds == 45.5

    def test_sync_result_json_roundtrip(self):
        """Test JSON serialization and deserialization"""
        track = TrackInfo(
            title="Song",
            artist="Artist",
            duration=180.0,
            spotify_id="spotify123",
        )
        words = [SyncedWord(text="hello", start=0.0, end=1.5, confidence=0.95)]
        lines = [SyncedLine(text="hello", start=0.0, end=1.5, words=words)]
        original = SyncResult(
            track=track,
            lines=lines,
            confidence=0.92,
            timing_source="lrclib_synced",
            cached=False,
            processing_time_seconds=10.5,
        )

        # Serialize to JSON
        json_str = original.model_dump_json()
        assert isinstance(json_str, str)

        # Deserialize from JSON
        restored = SyncResult.model_validate_json(json_str)

        # Verify they're the same
        assert restored.track.title == original.track.title
        assert restored.track.artist == original.track.artist
        assert restored.track.spotify_id == original.track.spotify_id
        assert len(restored.lines) == len(original.lines)
        assert restored.lines[0].text == original.lines[0].text
        assert restored.lines[0].words[0].text == original.lines[0].words[0].text
        assert restored.confidence == original.confidence
        assert restored.timing_source == original.timing_source
        assert restored.cached == original.cached
        assert restored.processing_time_seconds == original.processing_time_seconds


class TestSyncRequest:
    def test_sync_request_with_url(self):
        req = SyncRequest(url="https://example.com/song.mp3")
        assert req.url == "https://example.com/song.mp3"
        assert req.title is None
        assert req.artist is None

    def test_sync_request_with_title_artist(self):
        req = SyncRequest(title="Song", artist="Artist")
        assert req.url is None
        assert req.title == "Song"
        assert req.artist == "Artist"

    def test_sync_request_all_none(self):
        req = SyncRequest()
        assert req.url is None
        assert req.title is None
        assert req.artist is None

    def test_sync_request_all_set(self):
        req = SyncRequest(
            url="https://example.com/song.mp3", title="Song", artist="Artist"
        )
        assert req.url == "https://example.com/song.mp3"
        assert req.title == "Song"
        assert req.artist == "Artist"


class TestSettings:
    def test_settings_defaults(self):
        """Test that Settings has correct defaults"""
        settings = Settings()
        assert settings.cache_dir == Path.home() / ".syncer"
        assert settings.db_path == Path.home() / ".syncer" / "cache.db"
        assert settings.ctc_device == "cpu"
        assert settings.ctc_model == "MMS_FA"
        assert settings.demucs_model == "htdemucs"
        assert settings.spotify_client_id == ""
        assert settings.spotify_client_secret == ""
        assert settings.temp_dir is None
        assert settings.max_song_duration == 600

    def test_settings_env_override(self, monkeypatch):
        """Test that environment variables override defaults"""
        monkeypatch.setenv("SYNCER_CTC_DEVICE", "cuda")
        monkeypatch.setenv("SYNCER_MAX_SONG_DURATION", "1200")

        settings = Settings()
        assert settings.ctc_device == "cuda"
        assert settings.max_song_duration == 1200

    def test_settings_cache_dir_contains_syncer(self):
        """Test that cache_dir contains .syncer"""
        settings = Settings()
        assert ".syncer" in str(settings.cache_dir)

    def test_settings_db_path_contains_syncer(self):
        """Test that db_path contains .syncer"""
        settings = Settings()
        assert ".syncer" in str(settings.db_path)
        assert "cache.db" in str(settings.db_path)
