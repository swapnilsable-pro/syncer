"""Tests for YouTube audio extraction client."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from syncer.clients.youtube import (
    AudioResult,
    extract_audio,
    parse_youtube_url,
    search_youtube,
)


class TestParseYoutubeUrl:
    """Test URL parsing for various YouTube formats."""

    def test_standard_watch_url(self):
        """Parse standard youtube.com/watch?v= URL."""
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        assert parse_youtube_url(url) == "dQw4w9WgXcQ"

    def test_short_url(self):
        """Parse youtu.be short URL."""
        url = "https://youtu.be/dQw4w9WgXcQ"
        assert parse_youtube_url(url) == "dQw4w9WgXcQ"

    def test_music_youtube_url(self):
        """Parse music.youtube.com URL."""
        url = "https://music.youtube.com/watch?v=dQw4w9WgXcQ"
        assert parse_youtube_url(url) == "dQw4w9WgXcQ"

    def test_embed_url(self):
        """Parse youtube.com/embed/ URL."""
        url = "https://youtube.com/embed/dQw4w9WgXcQ"
        assert parse_youtube_url(url) == "dQw4w9WgXcQ"

    def test_shorts_url(self):
        """Parse youtube.com/shorts/ URL."""
        url = "https://youtube.com/shorts/dQw4w9WgXcQ"
        assert parse_youtube_url(url) == "dQw4w9WgXcQ"

    def test_invalid_url(self):
        """Return None for non-YouTube URL."""
        url = "https://example.com"
        assert parse_youtube_url(url) is None

    def test_empty_string(self):
        """Return None for empty string."""
        assert parse_youtube_url("") is None

    def test_none_input(self):
        """Return None for None input."""
        assert parse_youtube_url(None) is None


class TestExtractAudio:
    """Test audio extraction functionality."""

    def test_invalid_url_raises_value_error(self):
        """Raise ValueError for invalid URL."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(ValueError, match="Not a valid YouTube URL"):
                extract_audio("not_a_url", Path(tmpdir), 600)

    def test_duration_exceeds_max_raises_value_error(self):
        """Raise ValueError when video duration exceeds max_duration."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("syncer.clients.youtube.yt_dlp.YoutubeDL") as mock_ydl_class:
                # Mock the context manager
                mock_ydl = MagicMock()
                mock_ydl_class.return_value.__enter__.return_value = mock_ydl

                # Mock extract_info to return a video with duration > max_duration
                mock_ydl.extract_info.return_value = {
                    "duration": 700,  # 700 seconds > 600 max
                    "title": "Long Video",
                }

                with pytest.raises(ValueError, match="Video duration.*exceeds maximum"):
                    extract_audio(
                        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                        Path(tmpdir),
                        max_duration=600,
                    )

    def test_download_error_raises_runtime_error(self):
        """Raise RuntimeError when download fails."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch("syncer.clients.youtube.yt_dlp.YoutubeDL") as mock_ydl_class:
                mock_ydl = MagicMock()
                mock_ydl_class.return_value.__enter__.return_value = mock_ydl

                # Mock extract_info to raise DownloadError
                import yt_dlp

                mock_ydl.extract_info.side_effect = yt_dlp.utils.DownloadError(
                    "Video not found"
                )

                with pytest.raises(RuntimeError, match="Could not access video"):
                    extract_audio(
                        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                        Path(tmpdir),
                        max_duration=600,
                    )

    def test_successful_extraction_returns_audio_result(self):
        """Return AudioResult on successful extraction."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            with patch("syncer.clients.youtube.yt_dlp.YoutubeDL") as mock_ydl_class:
                mock_ydl = MagicMock()
                mock_ydl_class.return_value.__enter__.return_value = mock_ydl

                # Mock extract_info
                mock_ydl.extract_info.return_value = {
                    "duration": 300,
                    "title": "Test Video",
                }

                # Create a fake WAV file
                video_id = "dQw4w9WgXcQ"
                wav_file = tmpdir_path / f"{video_id}.wav"
                wav_file.write_text("fake audio data")

                result = extract_audio(
                    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    tmpdir_path,
                    max_duration=600,
                )

                assert isinstance(result, AudioResult)
                assert result.youtube_id == video_id
                assert result.title == "Test Video"
                assert result.duration == 300.0
                assert result.audio_path == wav_file


class TestSearchYoutube:
    """Test YouTube search functionality."""

    @pytest.mark.integration
    def test_search_youtube_returns_url(self):
        """Search YouTube and return a valid URL."""
        result = search_youtube("Yesterday Beatles")
        assert result is not None
        assert isinstance(result, str)
        assert "youtube.com" in result
        assert "watch?v=" in result

    def test_search_youtube_with_mock(self):
        """Test search_youtube with mocked yt_dlp."""
        with patch("syncer.clients.youtube.yt_dlp.YoutubeDL") as mock_ydl_class:
            mock_ydl = MagicMock()
            mock_ydl_class.return_value.__enter__.return_value = mock_ydl

            # Mock extract_info to return search results
            mock_ydl.extract_info.return_value = {
                "entries": [
                    {
                        "id": "dQw4w9WgXcQ",
                        "title": "Test Video",
                    }
                ]
            }

            result = search_youtube("test query")
            assert result == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

    def test_search_youtube_no_results(self):
        """Return None when search has no results."""
        with patch("syncer.clients.youtube.yt_dlp.YoutubeDL") as mock_ydl_class:
            mock_ydl = MagicMock()
            mock_ydl_class.return_value.__enter__.return_value = mock_ydl

            # Mock extract_info to return empty results
            mock_ydl.extract_info.return_value = {"entries": []}

            result = search_youtube("nonexistent query")
            assert result is None

    def test_search_youtube_exception_returns_none(self):
        """Return None when search raises exception."""
        with patch("syncer.clients.youtube.yt_dlp.YoutubeDL") as mock_ydl_class:
            mock_ydl = MagicMock()
            mock_ydl_class.return_value.__enter__.return_value = mock_ydl

            # Mock extract_info to raise exception
            mock_ydl.extract_info.side_effect = Exception("Network error")

            result = search_youtube("test query")
            assert result is None
