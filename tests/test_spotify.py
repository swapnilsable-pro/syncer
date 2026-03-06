"""Unit tests for Spotify client (all with mocked HTTP)."""

import unittest
from unittest.mock import MagicMock, patch

from syncer.clients.spotify import (
    get_client_token,
    parse_spotify_url,
    resolve_spotify_url,
)
from syncer.models import TrackInfo


class TestParseSpotifyUrl(unittest.TestCase):
    """Test URL/URI parsing."""

    def test_parse_https_url(self):
        """Parse standard HTTPS URL."""
        url = "https://open.spotify.com/track/6rqhFgbbKwnb9MLmUQDhG6"
        assert parse_spotify_url(url) == "6rqhFgbbKwnb9MLmUQDhG6"

    def test_parse_spotify_uri(self):
        """Parse spotify:track: URI format."""
        uri = "spotify:track:6rqhFgbbKwnb9MLmUQDhG6"
        assert parse_spotify_url(uri) == "6rqhFgbbKwnb9MLmUQDhG6"

    def test_parse_invalid_url(self):
        """Return None for non-Spotify URL."""
        assert parse_spotify_url("https://example.com") is None

    def test_parse_empty_string(self):
        """Return None for empty string."""
        assert parse_spotify_url("") is None

    def test_parse_url_with_query_params(self):
        """Strip query parameters from URL."""
        url = "https://open.spotify.com/track/6rqhFgbbKwnb9MLmUQDhG6?si=something"
        assert parse_spotify_url(url) == "6rqhFgbbKwnb9MLmUQDhG6"

    def test_parse_http_url(self):
        """Parse HTTP (non-HTTPS) URL."""
        url = "http://open.spotify.com/track/6rqhFgbbKwnb9MLmUQDhG6"
        assert parse_spotify_url(url) == "6rqhFgbbKwnb9MLmUQDhG6"


class TestGetClientToken(unittest.TestCase):
    """Test token acquisition."""

    def setUp(self):
        """Clear token cache before each test."""
        import syncer.clients.spotify as spotify_module
        spotify_module._token_cache["token"] = None
        spotify_module._token_cache["expires_at"] = 0
    """Test token acquisition."""

    def test_empty_credentials_no_http_call(self):
        """Return None for empty credentials without making HTTP call."""
        with patch("syncer.clients.spotify.httpx.Client") as mock_client_class:
            result = get_client_token("", "")
            assert result is None
            mock_client_class.assert_not_called()

    def test_missing_client_id(self):
        """Return None if client_id is empty."""
        with patch("syncer.clients.spotify.httpx.Client") as mock_client_class:
            result = get_client_token("", "secret")
            assert result is None
            mock_client_class.assert_not_called()

    def test_missing_client_secret(self):
        """Return None if client_secret is empty."""
        with patch("syncer.clients.spotify.httpx.Client") as mock_client_class:
            result = get_client_token("id", "")
            assert result is None
            mock_client_class.assert_not_called()

    @patch("syncer.clients.spotify.httpx.Client")
    def test_successful_token_fetch(self, mock_client_class):
        """Fetch token successfully."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "test_token_123",
            "expires_in": 3600,
        }
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client_class.return_value.__enter__.return_value = mock_client

        result = get_client_token("test_id", "test_secret")
        assert result == "test_token_123"

    @patch("syncer.clients.spotify.httpx.Client")
    def test_token_fetch_401_error(self, mock_client_class):
        """Return None on 401 error."""
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_client = MagicMock()
        mock_client.post.return_value = mock_response
        mock_client_class.return_value.__enter__.return_value = mock_client

        result = get_client_token("bad_id", "bad_secret")
        assert result is None

    @patch("syncer.clients.spotify.httpx.Client")
    def test_token_fetch_timeout(self, mock_client_class):
        """Return None on timeout."""
        import httpx

        mock_client = MagicMock()
        mock_client.post.side_effect = httpx.TimeoutException("timeout")
        mock_client_class.return_value.__enter__.return_value = mock_client

        result = get_client_token("test_id", "test_secret")
        assert result is None

    @patch("syncer.clients.spotify.httpx.Client")
    def test_token_fetch_request_error(self, mock_client_class):
        """Return None on request error."""
        import httpx

        mock_client = MagicMock()
        mock_client.post.side_effect = httpx.RequestError("connection error")
        mock_client_class.return_value.__enter__.return_value = mock_client

        result = get_client_token("test_id", "test_secret")
        assert result is None


class TestResolveSpotifyUrl(unittest.TestCase):
    """Test full URL resolution."""

    def test_invalid_url_returns_none(self):
        """Return None for invalid URL."""
        result = resolve_spotify_url("https://example.com", "id", "secret")
        assert result is None

    def test_empty_credentials_returns_none(self):
        """Return None when credentials are empty."""
        url = "https://open.spotify.com/track/6rqhFgbbKwnb9MLmUQDhG6"
        result = resolve_spotify_url(url, "", "")
        assert result is None

    @patch("syncer.clients.spotify.httpx.Client")
    def test_successful_resolution(self, mock_client_class):
        """Resolve URL to TrackInfo successfully."""
        # Mock token endpoint
        mock_token_response = MagicMock()
        mock_token_response.status_code = 200
        mock_token_response.json.return_value = {
            "access_token": "test_token",
            "expires_in": 3600,
        }

        # Mock track endpoint
        mock_track_response = MagicMock()
        mock_track_response.status_code = 200
        mock_track_response.json.return_value = {
            "name": "Test Track",
            "artists": [{"name": "Artist One"}, {"name": "Artist Two"}],
            "duration_ms": 180000,
            "external_ids": {"isrc": "USRC17607839"},
        }

        mock_client = MagicMock()
        mock_client.post.return_value = mock_token_response
        mock_client.get.return_value = mock_track_response
        mock_client_class.return_value.__enter__.return_value = mock_client

        url = "https://open.spotify.com/track/6rqhFgbbKwnb9MLmUQDhG6"
        result = resolve_spotify_url(url, "test_id", "test_secret")

        assert result is not None
        assert isinstance(result, TrackInfo)
        assert result.title == "Test Track"
        assert result.artist == "Artist One, Artist Two"
        assert result.duration == 180.0
        assert result.isrc == "USRC17607839"
        assert result.spotify_id == "6rqhFgbbKwnb9MLmUQDhG6"
        assert result.source_url == url

    @patch("syncer.clients.spotify.httpx.Client")
    def test_track_without_isrc(self, mock_client_class):
        """Handle track without ISRC gracefully."""
        mock_token_response = MagicMock()
        mock_token_response.status_code = 200
        mock_token_response.json.return_value = {
            "access_token": "test_token",
            "expires_in": 3600,
        }

        mock_track_response = MagicMock()
        mock_track_response.status_code = 200
        mock_track_response.json.return_value = {
            "name": "Test Track",
            "artists": [{"name": "Artist"}],
            "duration_ms": 180000,
            "external_ids": {},  # No ISRC
        }

        mock_client = MagicMock()
        mock_client.post.return_value = mock_token_response
        mock_client.get.return_value = mock_track_response
        mock_client_class.return_value.__enter__.return_value = mock_client

        url = "https://open.spotify.com/track/6rqhFgbbKwnb9MLmUQDhG6"
        result = resolve_spotify_url(url, "test_id", "test_secret")

        assert result is not None
        assert result.isrc is None

    @patch("syncer.clients.spotify.httpx.Client")
    def test_track_api_401_error(self, mock_client_class):
        """Return None on 401 from track API."""
        mock_token_response = MagicMock()
        mock_token_response.status_code = 200
        mock_token_response.json.return_value = {
            "access_token": "test_token",
            "expires_in": 3600,
        }

        mock_track_response = MagicMock()
        mock_track_response.status_code = 401

        mock_client = MagicMock()
        mock_client.post.return_value = mock_token_response
        mock_client.get.return_value = mock_track_response
        mock_client_class.return_value.__enter__.return_value = mock_client

        url = "https://open.spotify.com/track/6rqhFgbbKwnb9MLmUQDhG6"
        result = resolve_spotify_url(url, "test_id", "test_secret")

        assert result is None

    @patch("syncer.clients.spotify.httpx.Client")
    def test_track_api_timeout(self, mock_client_class):
        """Return None on timeout from track API."""
        import httpx

        mock_token_response = MagicMock()
        mock_token_response.status_code = 200
        mock_token_response.json.return_value = {
            "access_token": "test_token",
            "expires_in": 3600,
        }

        mock_client = MagicMock()
        mock_client.post.return_value = mock_token_response
        mock_client.get.side_effect = httpx.TimeoutException("timeout")
        mock_client_class.return_value.__enter__.return_value = mock_client

        url = "https://open.spotify.com/track/6rqhFgbbKwnb9MLmUQDhG6"
        result = resolve_spotify_url(url, "test_id", "test_secret")

        assert result is None

    @patch("syncer.clients.spotify.httpx.Client")
    def test_single_artist(self, mock_client_class):
        """Handle track with single artist."""
        mock_token_response = MagicMock()
        mock_token_response.status_code = 200
        mock_token_response.json.return_value = {
            "access_token": "test_token",
            "expires_in": 3600,
        }

        mock_track_response = MagicMock()
        mock_track_response.status_code = 200
        mock_track_response.json.return_value = {
            "name": "Solo Track",
            "artists": [{"name": "Solo Artist"}],
            "duration_ms": 240000,
            "external_ids": {"isrc": "USRC12345678"},
        }

        mock_client = MagicMock()
        mock_client.post.return_value = mock_token_response
        mock_client.get.return_value = mock_track_response
        mock_client_class.return_value.__enter__.return_value = mock_client

        url = "https://open.spotify.com/track/abc123"
        result = resolve_spotify_url(url, "test_id", "test_secret")

        assert result is not None
        assert result.artist == "Solo Artist"

    @patch("syncer.clients.spotify.httpx.Client")
    def test_no_artists(self, mock_client_class):
        """Handle track with no artists."""
        mock_token_response = MagicMock()
        mock_token_response.status_code = 200
        mock_token_response.json.return_value = {
            "access_token": "test_token",
            "expires_in": 3600,
        }

        mock_track_response = MagicMock()
        mock_track_response.status_code = 200
        mock_track_response.json.return_value = {
            "name": "Unknown Track",
            "artists": [],
            "duration_ms": 180000,
            "external_ids": {},
        }

        mock_client = MagicMock()
        mock_client.post.return_value = mock_token_response
        mock_client.get.return_value = mock_track_response
        mock_client_class.return_value.__enter__.return_value = mock_client

        url = "https://open.spotify.com/track/xyz789"
        result = resolve_spotify_url(url, "test_id", "test_secret")

        assert result is not None
        assert result.artist == ""


if __name__ == "__main__":
    unittest.main()
