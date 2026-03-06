"""Tests for LRCLIB client and LRC parser."""

import pytest
from unittest.mock import patch, MagicMock

from syncer.clients.lrclib import parse_lrc, fetch_lyrics, LrcLibResult


class TestParseLrc:
    """Test LRC format parser."""

    def test_parse_basic_two_lines(self):
        """Test parsing two basic lines with timestamps."""
        lrc_text = "[00:17.12] Hello\n[00:19.50] World"
        result = parse_lrc(lrc_text)

        assert len(result) == 2
        assert result[0].text == "Hello"
        assert result[0].start == 17.12
        assert result[0].end == 19.50
        assert result[0].words == []

        assert result[1].text == "World"
        assert result[1].start == 19.50
        assert result[1].end == 24.50  # 19.50 + 5.0

    def test_parse_skip_metadata(self):
        """Test that metadata tags are skipped."""
        lrc_text = "[ti:Test]\n[ar:Artist]\n[00:01.00] First line"
        result = parse_lrc(lrc_text)

        assert len(result) == 1
        assert result[0].text == "First line"
        assert result[0].start == 1.0

    def test_parse_empty_string(self):
        """Test parsing empty string returns empty list."""
        result = parse_lrc("")
        assert result == []

    def test_parse_whitespace_only(self):
        """Test parsing whitespace-only string returns empty list."""
        result = parse_lrc("   \n  \n  ")
        assert result == []

    def test_parse_single_line(self):
        """Test parsing single line gets 5s duration."""
        lrc_text = "[00:01.00] Only line"
        result = parse_lrc(lrc_text)

        assert len(result) == 1
        assert result[0].text == "Only line"
        assert result[0].start == 1.0
        assert result[0].end == 6.0  # 1.0 + 5.0

    def test_parse_milliseconds(self):
        """Test parsing 3-digit milliseconds."""
        lrc_text = "[00:01.500] First\n[00:02.750] Second"
        result = parse_lrc(lrc_text)

        assert len(result) == 2
        assert result[0].start == 1.5
        assert result[1].start == 2.75

    def test_parse_multiple_timestamps_per_line(self):
        """Test that only first timestamp is used."""
        lrc_text = "[00:01.00] First [00:02.00] part"
        result = parse_lrc(lrc_text)

        assert len(result) == 1
        assert result[0].text == "First  part"  # Both timestamps removed
        assert result[0].start == 1.0

    def test_parse_skip_lines_without_timestamp(self):
        """Test that lines without timestamps are skipped."""
        lrc_text = "[00:01.00] First\nNo timestamp here\n[00:02.00] Second"
        result = parse_lrc(lrc_text)

        assert len(result) == 2
        assert result[0].text == "First"
        assert result[1].text == "Second"

    def test_parse_skip_empty_text_lines(self):
        """Test that lines with only timestamps are skipped."""
        lrc_text = "[00:01.00]\n[00:02.00] Valid"
        result = parse_lrc(lrc_text)

        assert len(result) == 1
        assert result[0].text == "Valid"


class TestFetchLyricsWithMocks:
    """Test fetch_lyrics with mocked HTTP."""

    @patch("syncer.clients.lrclib.httpx.Client")
    def test_fetch_exact_match_success(self, mock_client_class):
        """Test successful exact match fetch."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "trackName": "Yesterday",
            "artistName": "The Beatles",
            "albumName": "Help!",
            "duration": 125.5,
            "instrumental": False,
            "syncedLyrics": "[00:00.00] Yesterday",
            "plainLyrics": "Yesterday",
        }
        mock_client.get.return_value = mock_response

        result = fetch_lyrics("Yesterday", "The Beatles", 125.5)

        assert result is not None
        assert result.track_name == "Yesterday"
        assert result.artist_name == "The Beatles"
        assert result.album_name == "Help!"
        assert result.duration == 125.5
        assert result.synced_lyrics == "[00:00.00] Yesterday"
        assert result.plain_lyrics == "Yesterday"
        assert result.instrumental is False

    @patch("syncer.clients.lrclib.httpx.Client")
    def test_fetch_instrumental_track(self, mock_client_class):
        """Test fetching instrumental track."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "trackName": "Instrumental Song",
            "artistName": "Artist",
            "albumName": None,
            "duration": 180.0,
            "instrumental": True,
        }
        mock_client.get.return_value = mock_response

        result = fetch_lyrics("Instrumental Song", "Artist")

        assert result is not None
        assert result.instrumental is True
        assert result.synced_lyrics is None
        assert result.plain_lyrics is None

    @patch("syncer.clients.lrclib.httpx.Client")
    def test_fetch_fallback_to_search(self, mock_client_class):
        """Test fallback to search when exact match not found."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        # First call (exact get) returns 404
        mock_get_response = MagicMock()
        mock_get_response.status_code = 404

        # Second call (search) returns results
        mock_search_response = MagicMock()
        mock_search_response.status_code = 200
        mock_search_response.json.return_value = [
            {
                "trackName": "Song Title",
                "artistName": "Artist Name",
                "albumName": "Album",
                "duration": 200.0,
                "instrumental": False,
                "syncedLyrics": "[00:00.00] Lyrics",
                "plainLyrics": "Lyrics",
            }
        ]

        mock_client.get.side_effect = [mock_get_response, mock_search_response]

        result = fetch_lyrics("Song Title", "Artist Name")

        assert result is not None
        assert result.track_name == "Song Title"
        assert result.synced_lyrics == "[00:00.00] Lyrics"

    @patch("syncer.clients.lrclib.httpx.Client")
    def test_fetch_timeout_returns_none(self, mock_client_class):
        """Test that timeout exception returns None."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        import httpx

        mock_client.get.side_effect = httpx.TimeoutException("Timeout")

        result = fetch_lyrics("Song", "Artist")

        assert result is None

    @patch("syncer.clients.lrclib.httpx.Client")
    def test_fetch_request_error_returns_none(self, mock_client_class):
        """Test that request error returns None."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        import httpx

        mock_client.get.side_effect = httpx.RequestError("Connection error")

        result = fetch_lyrics("Song", "Artist")

        assert result is None

    @patch("syncer.clients.lrclib.httpx.Client")
    def test_fetch_not_found_no_search_results(self, mock_client_class):
        """Test that 404 with no search results returns None."""
        mock_client = MagicMock()
        mock_client_class.return_value.__enter__.return_value = mock_client

        # First call (exact get) returns 404
        mock_get_response = MagicMock()
        mock_get_response.status_code = 404

        # Second call (search) returns empty results
        mock_search_response = MagicMock()
        mock_search_response.status_code = 200
        mock_search_response.json.return_value = []

        mock_client.get.side_effect = [mock_get_response, mock_search_response]

        result = fetch_lyrics("Nonexistent", "Song")

        assert result is None


class TestFetchLyricsIntegration:
    """Integration tests with real network (marked to skip by default)."""

    @pytest.mark.integration
    def test_fetch_real_beatles_yesterday(self):
        """Test fetching real lyrics from LRCLIB."""
        result = fetch_lyrics("Yesterday", "The Beatles")

        assert result is not None
        assert result.track_name is not None
        assert result.artist_name is not None
        # May or may not have synced lyrics depending on LRCLIB content
