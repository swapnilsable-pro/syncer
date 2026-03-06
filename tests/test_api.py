"""Tests for the FastAPI REST API endpoints."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from syncer.api import app
from syncer.models import SyncResult, SyncedLine, TrackInfo


def _make_sync_result(**overrides) -> SyncResult:
    """Create a valid SyncResult for testing."""
    defaults = {
        "track": TrackInfo(title="Test Song", artist="Test Artist", duration=180.0),
        "lines": [],
        "confidence": 0.9,
        "timing_source": "lrclib_synced",
        "cached": False,
        "processing_time_seconds": 1.0,
    }
    defaults.update(overrides)
    return SyncResult(**defaults)


# --- Health endpoint ---


def test_health_pipeline_loaded():
    with patch("syncer.api._pipeline", MagicMock()):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["models_loaded"] is True


def test_health_pipeline_not_loaded():
    with patch("syncer.api._pipeline", None):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["models_loaded"] is False


# --- Sync endpoint ---


def test_sync_endpoint_success():
    mock_pipeline = MagicMock()
    result = _make_sync_result()
    mock_pipeline.sync.return_value = result

    with patch("syncer.api._pipeline", mock_pipeline):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/api/sync", json={"title": "Test Song", "artist": "Test Artist"}
        )
        assert response.status_code == 200
        data = response.json()
        assert data["track"]["title"] == "Test Song"
        assert data["confidence"] == 0.9
        assert data["timing_source"] == "lrclib_synced"


def test_sync_endpoint_with_url():
    mock_pipeline = MagicMock()
    result = _make_sync_result()
    mock_pipeline.sync.return_value = result

    with patch("syncer.api._pipeline", mock_pipeline):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/api/sync",
            json={"url": "https://www.youtube.com/watch?v=dQw4w9WgXcQ"},
        )
        assert response.status_code == 200
        mock_pipeline.sync.assert_called_once()


def test_sync_endpoint_value_error():
    mock_pipeline = MagicMock()
    mock_pipeline.sync.side_effect = ValueError("Must provide url, title, or artist")

    with patch("syncer.api._pipeline", mock_pipeline):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/api/sync", json={"title": "Test"})
        assert response.status_code == 422
        assert "Must provide url, title, or artist" in response.json()["detail"]


def test_sync_endpoint_runtime_error():
    mock_pipeline = MagicMock()
    mock_pipeline.sync.side_effect = RuntimeError("Could not download audio")

    with patch("syncer.api._pipeline", mock_pipeline):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/api/sync", json={"title": "Test"})
        assert response.status_code == 500
        assert "Could not download audio" in response.json()["detail"]


def test_sync_endpoint_pipeline_not_initialized():
    with patch("syncer.api._pipeline", None):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/api/sync", json={"title": "Test"})
        assert response.status_code == 503


# --- Cache endpoint ---


def test_cache_endpoint_found():
    mock_pipeline = MagicMock()
    result = _make_sync_result(cached=True)
    mock_pipeline.cache.get_by_id.return_value = result

    with patch("syncer.api._pipeline", mock_pipeline):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/cache/abc123")
        assert response.status_code == 200
        data = response.json()
        assert data["track"]["title"] == "Test Song"
        assert data["cached"] is True
        mock_pipeline.cache.get_by_id.assert_called_once_with("abc123")


def test_cache_endpoint_not_found():
    mock_pipeline = MagicMock()
    mock_pipeline.cache.get_by_id.return_value = None

    with patch("syncer.api._pipeline", mock_pipeline):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/cache/nonexistent")
        assert response.status_code == 404
        assert "Track not found in cache" in response.json()["detail"]


def test_cache_endpoint_pipeline_not_initialized():
    with patch("syncer.api._pipeline", None):
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/cache/abc123")
        assert response.status_code == 503
