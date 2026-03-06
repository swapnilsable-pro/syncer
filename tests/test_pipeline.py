"""Tests for SyncPipeline orchestrator — all sub-modules mocked."""

import time
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from syncer.config import Settings
from syncer.models import SyncRequest, SyncResult, SyncedLine, SyncedWord, TrackInfo
from syncer.pipeline import SyncPipeline


# --- Helpers ---


@dataclass
class FakeAudioResult:
    audio_path: Path
    title: str
    duration: float
    youtube_id: str


@dataclass
class FakeAlignedWord:
    word: str
    start: float
    end: float
    score: float = 0.9


@dataclass
class FakeLrcLibResult:
    track_name: str
    artist_name: str
    album_name: str | None
    duration: float | None
    synced_lyrics: str | None
    plain_lyrics: str | None
    instrumental: bool


def _make_settings(tmp_path: Path) -> Settings:
    return Settings(
        db_path=tmp_path / "cache.db",
        cache_dir=tmp_path,
        whisperx_model="base",
        whisperx_device="cpu",
        whisperx_compute_type="float32",
        demucs_model="htdemucs",
        spotify_client_id="",
        spotify_client_secret="",
    )


def _make_synced_lines() -> list[SyncedLine]:
    return [
        SyncedLine(
            text="Hello world",
            start=0.0,
            end=2.0,
            words=[
                SyncedWord(text="Hello", start=0.0, end=1.0, confidence=0.9),
                SyncedWord(text="world", start=1.0, end=2.0, confidence=0.9),
            ],
        )
    ]


def _make_asr_words() -> list[FakeAlignedWord]:
    return [
        FakeAlignedWord(word="Hello", start=0.0, end=1.0, score=0.9),
        FakeAlignedWord(word="world", start=1.0, end=2.0, score=0.9),
    ]


# Patch targets (where they're imported in pipeline module)
_P_SEPARATOR = "syncer.pipeline.VocalSeparator"
_P_ALIGNER = "syncer.pipeline.WordAligner"
_P_FETCH_LYRICS = "syncer.pipeline.fetch_lyrics"
_P_PARSE_LRC = "syncer.pipeline.parse_lrc"
_P_RESOLVE_SPOTIFY = "syncer.pipeline.resolve_spotify_url"
_P_EXTRACT_AUDIO = "syncer.pipeline.extract_audio"
_P_SEARCH_YOUTUBE = "syncer.pipeline.search_youtube"
_P_PARSE_YOUTUBE = "syncer.pipeline.parse_youtube_url"
_P_SNAP = "syncer.pipeline.snap_words_to_lyrics"
_P_CONFIDENCE = "syncer.pipeline.compute_confidence"


@pytest.fixture
def settings(tmp_path):
    return _make_settings(tmp_path)


# --- Tests ---


class TestCacheHit:
    """Cache hit path: pre-populated cache returns cached result."""

    @patch(_P_ALIGNER)
    @patch(_P_SEPARATOR)
    def test_cache_hit_returns_fast(
        self,
        mock_sep_cls,
        mock_align_cls,
        settings,
    ):
        """Pre-populate cache via CacheManager, verify sync() returns cached result quickly."""
        from syncer.cache import CacheManager

        # Pre-populate cache with a result matching title/artist/duration=0.0
        # (title+artist requests resolve to duration=0.0 before audio extraction)
        cache = CacheManager(settings.db_path)
        stored = SyncResult(
            track=TrackInfo(
                title="Test Song",
                artist="Test Artist",
                duration=0.0,
            ),
            lines=_make_synced_lines(),
            confidence=0.9,
            timing_source="whisperx_only",
            cached=False,
            processing_time_seconds=1.5,
        )
        cache.store_result(stored)

        pipeline = SyncPipeline(settings)
        request = SyncRequest(title="Test Song", artist="Test Artist")

        start = time.time()
        result = pipeline.sync(request)
        elapsed = time.time() - start

        assert result.cached is True
        assert elapsed < 0.5  # Cache hit should be fast
        assert result.track.title == "Test Song"
        assert result.confidence == 0.9


class TestYouTubeFullPipeline:
    """YouTube URL triggers full pipeline with all sub-modules."""

    @patch(_P_ALIGNER)
    @patch(_P_SEPARATOR)
    @patch(_P_FETCH_LYRICS)
    @patch(_P_EXTRACT_AUDIO)
    @patch(_P_PARSE_YOUTUBE)
    @patch(_P_SNAP)
    @patch(_P_CONFIDENCE)
    def test_youtube_url_full_pipeline(
        self,
        mock_conf,
        mock_snap,
        mock_parse_yt,
        mock_extract,
        mock_fetch,
        mock_sep_cls,
        mock_align_cls,
        settings,
    ):
        """Mock all sub-modules, verify orchestration order for YouTube URL."""
        mock_parse_yt.return_value = "dQw4w9WgXcQ"
        mock_extract.return_value = FakeAudioResult(
            audio_path=Path("/fake/audio.wav"),
            title="Never Gonna Give You Up",
            duration=213.0,
            youtube_id="dQw4w9WgXcQ",
        )
        mock_fetch.return_value = FakeLrcLibResult(
            track_name="Never Gonna Give You Up",
            artist_name="Rick Astley",
            album_name=None,
            duration=213.0,
            synced_lyrics=None,
            plain_lyrics="Never gonna give you up\nNever gonna let you down",
            instrumental=False,
        )
        mock_sep_cls.return_value.separate.return_value = Path("/fake/vocals.wav")
        asr_words = _make_asr_words()
        mock_align_cls.return_value.align.return_value = asr_words
        mock_snap.return_value = _make_synced_lines()
        mock_conf.return_value = 0.85

        pipeline = SyncPipeline(settings)
        request = SyncRequest(url="https://www.youtube.com/watch?v=dQw4w9WgXcQ")

        result = pipeline.sync(request)

        assert result.cached is False
        assert result.confidence == 0.85
        assert result.timing_source == "lrclib_enhanced"
        assert len(result.lines) > 0
        # Verify sub-modules were called
        mock_extract.assert_called_once()
        mock_sep_cls.return_value.separate.assert_called_once()
        mock_align_cls.return_value.align.assert_called_once()
        mock_snap.assert_called_once()


class TestLrcLibSyncedPath:
    """LRCLIB returns synced lyrics — timing_source reflects this."""

    @patch(_P_ALIGNER)
    @patch(_P_SEPARATOR)
    @patch(_P_FETCH_LYRICS)
    @patch(_P_EXTRACT_AUDIO)
    @patch(_P_SEARCH_YOUTUBE)
    @patch(_P_PARSE_LRC)
    @patch(_P_SNAP)
    @patch(_P_CONFIDENCE)
    def test_lrclib_synced_enhanced_with_alignment(
        self,
        mock_conf,
        mock_snap,
        mock_parse_lrc,
        mock_search,
        mock_extract,
        mock_fetch,
        mock_sep_cls,
        mock_align_cls,
        settings,
    ):
        """LRCLIB synced lyrics + alignment = lrclib_enhanced."""
        synced_lines = _make_synced_lines()
        mock_parse_lrc.return_value = synced_lines
        mock_fetch.return_value = FakeLrcLibResult(
            track_name="Test",
            artist_name="Artist",
            album_name=None,
            duration=180.0,
            synced_lyrics="[00:00.00] Hello world",
            plain_lyrics=None,
            instrumental=False,
        )
        mock_search.return_value = "https://www.youtube.com/watch?v=abc12345678"
        mock_extract.return_value = FakeAudioResult(
            audio_path=Path("/fake/audio.wav"),
            title="Test",
            duration=180.0,
            youtube_id="abc12345678",
        )
        mock_sep_cls.return_value.separate.return_value = Path("/fake/vocals.wav")
        mock_align_cls.return_value.align.return_value = _make_asr_words()
        mock_snap.return_value = synced_lines
        mock_conf.return_value = 0.9

        pipeline = SyncPipeline(settings)
        request = SyncRequest(title="Test", artist="Artist")
        result = pipeline.sync(request)

        # Synced lyrics + alignment → enhanced
        assert result.timing_source == "lrclib_enhanced"
        assert result.confidence == 0.9


class TestAudioExtractionFailure:
    """yt-dlp fails → RuntimeError with clear message."""

    @patch(_P_ALIGNER)
    @patch(_P_SEPARATOR)
    @patch(_P_FETCH_LYRICS)
    @patch(_P_EXTRACT_AUDIO)
    @patch(_P_SEARCH_YOUTUBE)
    def test_audio_extraction_failure_no_lyrics(
        self,
        mock_search,
        mock_extract,
        mock_fetch,
        mock_sep_cls,
        mock_align_cls,
        settings,
    ):
        """Audio extraction fails without synced lyrics → RuntimeError."""
        mock_fetch.return_value = None
        mock_search.return_value = "https://www.youtube.com/watch?v=abc12345678"
        mock_extract.side_effect = RuntimeError("Download failed: 403 Forbidden")

        pipeline = SyncPipeline(settings)
        request = SyncRequest(title="Test Song", artist="Test Artist")

        with pytest.raises(RuntimeError, match="Could not download audio"):
            pipeline.sync(request)

    @patch(_P_ALIGNER)
    @patch(_P_SEPARATOR)
    @patch(_P_FETCH_LYRICS)
    @patch(_P_EXTRACT_AUDIO)
    @patch(_P_SEARCH_YOUTUBE)
    @patch(_P_PARSE_LRC)
    @patch(_P_CONFIDENCE)
    def test_audio_failure_with_synced_lyrics_returns_lyrics(
        self,
        mock_conf,
        mock_parse_lrc,
        mock_search,
        mock_extract,
        mock_fetch,
        mock_sep_cls,
        mock_align_cls,
        settings,
    ):
        """Audio extraction fails but we have synced lyrics → return them."""
        synced_lines = _make_synced_lines()
        mock_parse_lrc.return_value = synced_lines
        mock_fetch.return_value = FakeLrcLibResult(
            track_name="Test",
            artist_name="Artist",
            album_name=None,
            duration=180.0,
            synced_lyrics="[00:00.00] Hello world",
            plain_lyrics=None,
            instrumental=False,
        )
        mock_search.return_value = "https://www.youtube.com/watch?v=abc12345678"
        mock_extract.side_effect = RuntimeError("Download failed")
        mock_conf.return_value = 0.8

        pipeline = SyncPipeline(settings)
        request = SyncRequest(title="Test", artist="Artist")
        result = pipeline.sync(request)

        assert result.timing_source == "lrclib_synced"
        assert len(result.lines) > 0
        assert result.cached is False


class TestTitleArtistQuery:
    """title+artist input → searches YouTube."""

    @patch(_P_ALIGNER)
    @patch(_P_SEPARATOR)
    @patch(_P_FETCH_LYRICS)
    @patch(_P_EXTRACT_AUDIO)
    @patch(_P_SEARCH_YOUTUBE)
    @patch(_P_SNAP)
    @patch(_P_CONFIDENCE)
    def test_title_artist_searches_youtube(
        self,
        mock_conf,
        mock_snap,
        mock_search,
        mock_extract,
        mock_fetch,
        mock_sep_cls,
        mock_align_cls,
        settings,
    ):
        """Title + artist → search_youtube called with correct query."""
        mock_fetch.return_value = None
        mock_search.return_value = "https://www.youtube.com/watch?v=abc12345678"
        mock_extract.return_value = FakeAudioResult(
            audio_path=Path("/fake/audio.wav"),
            title="Test Song",
            duration=200.0,
            youtube_id="abc12345678",
        )
        mock_sep_cls.return_value.separate.return_value = Path("/fake/vocals.wav")
        mock_align_cls.return_value.align.return_value = _make_asr_words()
        mock_snap.return_value = []
        mock_conf.return_value = 0.0

        pipeline = SyncPipeline(settings)
        request = SyncRequest(title="Test Song", artist="Test Artist")
        pipeline.sync(request)

        mock_search.assert_called_once_with("Test Song Test Artist")


class TestInvalidInput:
    """Invalid input returns clear error."""

    @patch(_P_ALIGNER)
    @patch(_P_SEPARATOR)
    def test_no_url_no_title_raises(self, mock_sep_cls, mock_align_cls, settings):
        """Empty request → ValueError."""
        pipeline = SyncPipeline(settings)
        request = SyncRequest()

        with pytest.raises(ValueError, match="Must provide url, title, or artist"):
            pipeline.sync(request)

    @patch(_P_ALIGNER)
    @patch(_P_SEPARATOR)
    def test_unsupported_url_raises(self, mock_sep_cls, mock_align_cls, settings):
        """Unsupported URL format → ValueError."""
        pipeline = SyncPipeline(settings)
        request = SyncRequest(url="https://example.com/not-a-music-service")

        with pytest.raises(ValueError, match="Unsupported URL format"):
            pipeline.sync(request)


class TestSpotifyPath:
    """Spotify URL → resolve_spotify_url then search_youtube."""

    @patch(_P_ALIGNER)
    @patch(_P_SEPARATOR)
    @patch(_P_FETCH_LYRICS)
    @patch(_P_EXTRACT_AUDIO)
    @patch(_P_SEARCH_YOUTUBE)
    @patch(_P_RESOLVE_SPOTIFY)
    @patch(_P_SNAP)
    @patch(_P_CONFIDENCE)
    def test_spotify_url_resolves_and_searches(
        self,
        mock_conf,
        mock_snap,
        mock_resolve,
        mock_search,
        mock_extract,
        mock_fetch,
        mock_sep_cls,
        mock_align_cls,
        settings,
    ):
        """Spotify URL → resolve metadata → search YouTube → full pipeline."""
        mock_resolve.return_value = TrackInfo(
            title="Bohemian Rhapsody",
            artist="Queen",
            duration=354.0,
            isrc="GBUM71029604",
            spotify_id="3z8h0TU7ReDPLIbEnYhWZb",
        )
        mock_fetch.return_value = None
        mock_search.return_value = "https://www.youtube.com/watch?v=fJ9rUzIMcZQ"
        mock_extract.return_value = FakeAudioResult(
            audio_path=Path("/fake/audio.wav"),
            title="Bohemian Rhapsody",
            duration=354.0,
            youtube_id="fJ9rUzIMcZQ",
        )
        mock_sep_cls.return_value.separate.return_value = Path("/fake/vocals.wav")
        mock_align_cls.return_value.align.return_value = _make_asr_words()
        mock_snap.return_value = []
        mock_conf.return_value = 0.0

        pipeline = SyncPipeline(settings)
        request = SyncRequest(
            url="https://open.spotify.com/track/3z8h0TU7ReDPLIbEnYhWZb"
        )
        result = pipeline.sync(request)

        mock_resolve.assert_called_once()
        mock_search.assert_called_once_with("Bohemian Rhapsody Queen")
        assert result.track.title == "Bohemian Rhapsody"
        assert result.track.spotify_id == "3z8h0TU7ReDPLIbEnYhWZb"


class TestWhisperXOnlyPath:
    """No lyrics available → whisperx_only with ASR-derived lines."""

    @patch(_P_ALIGNER)
    @patch(_P_SEPARATOR)
    @patch(_P_FETCH_LYRICS)
    @patch(_P_EXTRACT_AUDIO)
    @patch(_P_SEARCH_YOUTUBE)
    @patch(_P_CONFIDENCE)
    def test_no_lyrics_uses_asr_only(
        self,
        mock_conf,
        mock_search,
        mock_extract,
        mock_fetch,
        mock_sep_cls,
        mock_align_cls,
        settings,
    ):
        """No LRCLIB result → whisperx_only with lines from ASR."""
        mock_fetch.return_value = None
        mock_search.return_value = "https://www.youtube.com/watch?v=abc12345678"
        mock_extract.return_value = FakeAudioResult(
            audio_path=Path("/fake/audio.wav"),
            title="Instrumental",
            duration=120.0,
            youtube_id="abc12345678",
        )
        mock_sep_cls.return_value.separate.return_value = Path("/fake/vocals.wav")
        mock_align_cls.return_value.align.return_value = _make_asr_words()
        mock_conf.return_value = 0.9

        pipeline = SyncPipeline(settings)
        request = SyncRequest(title="Instrumental", artist="Various")
        result = pipeline.sync(request)

        assert result.timing_source == "whisperx_only"
        # Lines are built from ASR words
        assert len(result.lines) > 0
        assert result.lines[0].text == "Hello world"


class TestSearchYouTubeFailure:
    """YouTube search returns None → RuntimeError."""

    @patch(_P_ALIGNER)
    @patch(_P_SEPARATOR)
    @patch(_P_FETCH_LYRICS)
    @patch(_P_SEARCH_YOUTUBE)
    def test_search_youtube_no_results(
        self,
        mock_search,
        mock_fetch,
        mock_sep_cls,
        mock_align_cls,
        settings,
    ):
        """search_youtube returns None → RuntimeError."""
        mock_fetch.return_value = None
        mock_search.return_value = None

        pipeline = SyncPipeline(settings)
        request = SyncRequest(title="Nonexistent Song", artist="Nobody")

        with pytest.raises(RuntimeError, match="Could not download audio"):
            pipeline.sync(request)
