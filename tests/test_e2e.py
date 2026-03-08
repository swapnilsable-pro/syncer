"""End-to-end tests with 5 reference songs. All tests require network + ML models.

Run with: pytest tests/test_e2e.py -v -m slow
"""

import time

import pytest

from syncer.models import SyncRequest, SyncResult


# ============================================================
# 5 Reference Song Tests
# ============================================================


@pytest.mark.slow
def test_yesterday_beatles(pipeline):
    """Simple song, should produce high confidence."""
    request = SyncRequest(title="Yesterday", artist="The Beatles")
    result = pipeline.sync(request)

    assert isinstance(result, SyncResult)
    assert result.track.title  # non-empty
    assert len(result.lines) > 5
    total_words = sum(len(line.words) for line in result.lines)
    assert total_words > 20
    assert result.confidence > 0.0
    assert result.timing_source in (
        "lrclib_synced",
        "ctc_aligned",
        "no_lyrics",
    )


@pytest.mark.slow
def test_shake_it_off_taylor_swift(pipeline):
    """Modern pop, good LRCLIB coverage."""
    request = SyncRequest(title="Shake It Off", artist="Taylor Swift")
    result = pipeline.sync(request)

    assert isinstance(result, SyncResult)
    assert len(result.lines) > 10
    assert result.confidence >= 0.0  # may be low but must be valid
    assert 0.0 <= result.confidence <= 1.0


@pytest.mark.slow
def test_never_gonna_give_you_up(pipeline):
    """Known YouTube URL test."""
    request = SyncRequest(url="https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    result = pipeline.sync(request)

    assert isinstance(result, SyncResult)
    assert len(result.lines) > 0
    assert result.track.youtube_id == "dQw4w9WgXcQ"
    assert 0.0 <= result.confidence <= 1.0


@pytest.mark.slow
def test_lose_yourself_eminem(pipeline):
    """Rap stress test — may have lower confidence."""
    request = SyncRequest(title="Lose Yourself", artist="Eminem")
    result = pipeline.sync(request)

    assert isinstance(result, SyncResult)
    assert len(result.lines) > 0  # produces output even if confidence is low
    assert 0.0 <= result.confidence <= 1.0


@pytest.mark.slow
def test_bohemian_rhapsody_queen(pipeline):
    """Complex structure, tempo changes."""
    request = SyncRequest(title="Bohemian Rhapsody", artist="Queen")
    result = pipeline.sync(request)

    assert isinstance(result, SyncResult)
    assert len(result.lines) > 20  # long song
    assert 0.0 <= result.confidence <= 1.0


# ============================================================
# Cache Test
# ============================================================


@pytest.mark.slow
def test_cache_hit_is_fast(pipeline):
    """Second request for same song returns cached result in <500ms."""
    request = SyncRequest(title="Yesterday", artist="The Beatles")

    # First request (may be slow)
    result1 = pipeline.sync(request)
    assert not result1.cached

    # Second request (should be fast)
    start = time.time()
    result2 = pipeline.sync(request)
    elapsed = time.time() - start

    assert result2.cached
    assert elapsed < 0.5  # <500ms
    assert len(result2.lines) == len(result1.lines)


# ============================================================
# API Test
# ============================================================


@pytest.mark.slow
def test_api_sync_endpoint(test_client):
    """API endpoint returns valid JSON response."""
    response = test_client.post(
        "/api/sync",
        json={"title": "Yesterday", "artist": "The Beatles"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "lines" in data
    assert "confidence" in data
    assert "timing_source" in data
    assert "track" in data
    assert len(data["lines"]) > 0


# ============================================================
# Error Tests
# ============================================================


@pytest.mark.slow
def test_invalid_url_returns_error(pipeline):
    """Invalid URL returns ValueError or RuntimeError, not crash."""
    request = SyncRequest(url="https://example.com/notavideo")
    with pytest.raises((ValueError, RuntimeError)):
        pipeline.sync(request)


@pytest.mark.slow
def test_empty_request_raises_value_error(pipeline):
    """Empty request (no url, title, or artist) raises ValueError."""
    request = SyncRequest()
    with pytest.raises(ValueError):
        pipeline.sync(request)
