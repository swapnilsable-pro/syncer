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
        mock_align_cls.return_value.align.return_value = MagicMock(words=asr_words, detected_language="en")
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
        mock_align_cls.return_value.align.return_value = MagicMock(words=_make_asr_words(), detected_language="en")
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
        mock_align_cls.return_value.align.return_value = MagicMock(words=_make_asr_words(), detected_language="en")
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
        mock_align_cls.return_value.align.return_value = MagicMock(words=_make_asr_words(), detected_language="en")
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
        mock_align_cls.return_value.align.return_value = MagicMock(words=_make_asr_words(), detected_language="en")
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


class TestParseVideoTitle:
    """_parse_video_title extracts artist/title from YouTube video titles."""

    def test_artist_dash_title(self):
        title, artist = SyncPipeline._parse_video_title("Rick Astley - Never Gonna Give You Up")
        assert title == "Never Gonna Give You Up"
        assert artist == "Rick Astley"

    def test_artist_dash_title_official_video(self):
        title, artist = SyncPipeline._parse_video_title(
            "Rick Astley - Never Gonna Give You Up (Official Music Video)"
        )
        assert title == "Never Gonna Give You Up"
        assert artist == "Rick Astley"

    def test_artist_dash_title_brackets(self):
        title, artist = SyncPipeline._parse_video_title(
            "Queen - Bohemian Rhapsody [Official Video]"
        )
        assert title == "Bohemian Rhapsody"
        assert artist == "Queen"

    def test_no_separator(self):
        title, artist = SyncPipeline._parse_video_title("Never Gonna Give You Up")
        assert title == "Never Gonna Give You Up"
        assert artist is None

    def test_lyrics_suffix(self):
        title, artist = SyncPipeline._parse_video_title(
            "Adele - Hello (Lyrics)"
        )
        assert title == "Hello"
        assert artist == "Adele"

    def test_pipe_suffix_stripped(self):
        title, artist = SyncPipeline._parse_video_title(
            "Coldplay - Yellow | Live at Glastonbury"
        )
        assert title == "Yellow"
        assert artist == "Coldplay"

    def test_official_audio(self):
        title, artist = SyncPipeline._parse_video_title(
            "Taylor Swift - Shake It Off (Official Audio)"
        )
        assert title == "Shake It Off"
        assert artist == "Taylor Swift"


class TestYouTubeMetadataExtraction:
    """YouTube URL with no title → metadata extracted from yt-dlp → LRCLIB retried."""

    @patch(_P_ALIGNER)
    @patch(_P_SEPARATOR)
    @patch(_P_FETCH_LYRICS)
    @patch(_P_EXTRACT_AUDIO)
    @patch(_P_PARSE_YOUTUBE)
    @patch(_P_PARSE_LRC)
    @patch(_P_SNAP)
    @patch(_P_CONFIDENCE)
    def test_youtube_url_extracts_metadata_and_retries_lrclib(
        self,
        mock_conf,
        mock_snap,
        mock_parse_lrc,
        mock_parse_yt,
        mock_extract,
        mock_fetch,
        mock_sep_cls,
        mock_align_cls,
        settings,
    ):
        """YouTube URL → title=Unknown → extract_audio → parse title → retry LRCLIB."""
        mock_parse_yt.return_value = "dQw4w9WgXcQ"
        mock_extract.return_value = FakeAudioResult(
            audio_path=Path("/fake/audio.wav"),
            title="Rick Astley - Never Gonna Give You Up (Official Music Video)",
            duration=213.0,
            youtube_id="dQw4w9WgXcQ",
        )
        # First LRCLIB call with "Unknown" → None; second with real metadata → result
        synced_lines = _make_synced_lines()
        mock_fetch.side_effect = [
            None,  # First call with "Unknown" title
            FakeLrcLibResult(
                track_name="Never Gonna Give You Up",
                artist_name="Rick Astley",
                album_name=None,
                duration=213.0,
                synced_lyrics="[00:00.00] Hello world",
                plain_lyrics=None,
                instrumental=False,
            ),
        ]
        mock_parse_lrc.return_value = synced_lines
        mock_sep_cls.return_value.separate.return_value = Path("/fake/vocals.wav")
        mock_align_cls.return_value.align.return_value = MagicMock(words=_make_asr_words(), detected_language="en")
        mock_snap.return_value = synced_lines
        mock_conf.return_value = 0.9

        pipeline = SyncPipeline(settings)
        request = SyncRequest(url="https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        result = pipeline.sync(request)

        # Metadata should be extracted from video title
        assert result.track.title == "Never Gonna Give You Up"
        assert result.track.artist == "Rick Astley"
        # LRCLIB was called twice: once with Unknown, once with real metadata
        assert mock_fetch.call_count == 2
        # Second call used parsed metadata
        second_call = mock_fetch.call_args_list[1]
        assert second_call[0][0] == "Never Gonna Give You Up"
        assert second_call[0][1] == "Rick Astley"
        # Got synced lyrics from retry → enhanced after alignment
        assert result.timing_source == "lrclib_enhanced"

    @patch(_P_ALIGNER)
    @patch(_P_SEPARATOR)
    @patch(_P_FETCH_LYRICS)
    @patch(_P_EXTRACT_AUDIO)
    @patch(_P_PARSE_YOUTUBE)
    @patch(_P_CONFIDENCE)
    def test_youtube_url_no_dash_in_title_uses_full_title(
        self,
        mock_conf,
        mock_parse_yt,
        mock_extract,
        mock_fetch,
        mock_sep_cls,
        mock_align_cls,
        settings,
    ):
        """YouTube title without ' - ' → whole title used, artist stays Unknown."""
        mock_parse_yt.return_value = "abc12345678"
        mock_extract.return_value = FakeAudioResult(
            audio_path=Path("/fake/audio.wav"),
            title="Some Song Without Artist Separator",
            duration=180.0,
            youtube_id="abc12345678",
        )
        mock_fetch.side_effect = [None, None]  # No lyrics found either time
        mock_sep_cls.return_value.separate.return_value = Path("/fake/vocals.wav")
        mock_align_cls.return_value.align.return_value = MagicMock(words=_make_asr_words(), detected_language="en")
        mock_conf.return_value = 0.5

        pipeline = SyncPipeline(settings)
        request = SyncRequest(url="https://www.youtube.com/watch?v=abc12345678")
        result = pipeline.sync(request)

        assert result.track.title == "Some Song Without Artist Separator"
        assert result.track.artist == "Unknown"  # No artist parsed
        assert mock_fetch.call_count == 2


class TestLanguageParameter:
    """Language parameter is threaded through the pipeline."""

    @patch(_P_ALIGNER)
    @patch(_P_SEPARATOR)
    @patch(_P_FETCH_LYRICS)
    @patch(_P_EXTRACT_AUDIO)
    @patch(_P_SEARCH_YOUTUBE)
    @patch(_P_SNAP)
    @patch(_P_CONFIDENCE)
    def test_language_threaded_to_aligner(
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
        """language from SyncRequest is passed to aligner.align()."""
        mock_fetch.return_value = None
        mock_search.return_value = "https://www.youtube.com/watch?v=abc12345678"
        mock_extract.return_value = FakeAudioResult(
            audio_path=Path("/fake/audio.wav"),
            title="Test Song",
            duration=200.0,
            youtube_id="abc12345678",
        )
        mock_sep_cls.return_value.separate.return_value = Path("/fake/vocals.wav")
        mock_align_cls.return_value.align.return_value = MagicMock(words=_make_asr_words(), detected_language="hi")
        mock_snap.return_value = []
        mock_conf.return_value = 0.0

        pipeline = SyncPipeline(settings)
        request = SyncRequest(title="Test Song", language="hi")
        pipeline.sync(request)

        # Verify language was passed to aligner
        call_kwargs = mock_align_cls.return_value.align.call_args
        assert call_kwargs[1]["language"] == "hi"

    @patch(_P_ALIGNER)
    @patch(_P_SEPARATOR)
    @patch(_P_FETCH_LYRICS)
    @patch(_P_EXTRACT_AUDIO)
    @patch(_P_SEARCH_YOUTUBE)
    @patch(_P_CONFIDENCE)
    def test_detected_language_in_result(
        self,
        mock_conf,
        mock_search,
        mock_extract,
        mock_fetch,
        mock_sep_cls,
        mock_align_cls,
        settings,
    ):
        """detected_language from aligner appears in SyncResult."""
        mock_fetch.return_value = None
        mock_search.return_value = "https://www.youtube.com/watch?v=abc12345678"
        mock_extract.return_value = FakeAudioResult(
            audio_path=Path("/fake/audio.wav"),
            title="Test Song",
            duration=200.0,
            youtube_id="abc12345678",
        )
        mock_sep_cls.return_value.separate.return_value = Path("/fake/vocals.wav")
        mock_align_cls.return_value.align.return_value = MagicMock(words=_make_asr_words(), detected_language="en")
        mock_conf.return_value = 0.9

        pipeline = SyncPipeline(settings)
        request = SyncRequest(title="Test Song", artist="Test Artist")
        result = pipeline.sync(request)

        assert result.detected_language == "en"
