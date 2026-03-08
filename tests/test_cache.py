import pytest
from pathlib import Path

from syncer.cache import CacheManager, generate_track_id
from syncer.models import SyncResult, TrackInfo, SyncedLine, SyncedWord


@pytest.fixture
def cache(tmp_path):
    """Create an in-memory cache for testing."""
    return CacheManager(tmp_path / "test.db")


@pytest.fixture
def sample_sync_result():
    """Create a sample SyncResult for testing."""
    track = TrackInfo(
        title="Yesterday",
        artist="The Beatles",
        duration=125.0,
        isrc="GBUM71505001",
        spotify_id="spotify_id_123",
        youtube_id="youtube_id_456",
    )
    lines = [
        SyncedLine(
            text="Yesterday, all my troubles seemed so far away",
            start=0.0,
            end=5.0,
            words=[
                SyncedWord(text="Yesterday", start=0.0, end=1.0, confidence=0.95),
                SyncedWord(text="all", start=1.5, end=2.0, confidence=0.92),
            ],
        ),
        SyncedLine(
            text="Now it looks as though they're here to stay",
            start=5.5,
            end=10.0,
            words=[
                SyncedWord(text="Now", start=5.5, end=6.0, confidence=0.98),
            ],
        ),
    ]
    return SyncResult(
        track=track,
        lines=lines,
        confidence=0.94,
        timing_source="lrclib_synced",
        processing_time_seconds=2.5,
    )


def test_generate_track_id_deterministic():
    """Test that generate_track_id produces deterministic output."""
    id1 = generate_track_id("Yesterday", "The Beatles", 125.0)
    id2 = generate_track_id("Yesterday", "The Beatles", 125.0)
    assert id1 == id2, "Same input should produce same track ID"


def test_generate_track_id_case_insensitive():
    """Test that generate_track_id is case-insensitive."""
    id1 = generate_track_id("Yesterday", "The Beatles", 125.0)
    id2 = generate_track_id("yesterday", "the beatles", 125.0)
    assert id1 == id2, "Track ID should be case-insensitive"


def test_generate_track_id_whitespace_insensitive():
    """Test that generate_track_id strips whitespace."""
    id1 = generate_track_id("Yesterday", "The Beatles", 125.0)
    id2 = generate_track_id("  Yesterday  ", "  The Beatles  ", 125.0)
    assert id1 == id2, "Track ID should strip whitespace"


def test_store_and_retrieve_sync_result(cache, sample_sync_result):
    """Test round-trip: store SyncResult → get_cached → compare fields."""
    # Store the result
    cache.store_result(sample_sync_result)

    # Retrieve it
    retrieved = cache.get_cached("Yesterday", "The Beatles", 125.0)

    # Verify it's not None
    assert retrieved is not None, "Should retrieve stored result"

    # Verify key fields match
    assert retrieved.track.title == sample_sync_result.track.title
    assert retrieved.track.artist == sample_sync_result.track.artist
    assert retrieved.confidence == sample_sync_result.confidence
    assert retrieved.timing_source == sample_sync_result.timing_source
    assert len(retrieved.lines) == len(sample_sync_result.lines)


def test_retrieved_result_has_cached_flag(cache, sample_sync_result):
    """Test that retrieved result has cached=True."""
    cache.store_result(sample_sync_result)
    retrieved = cache.get_cached("Yesterday", "The Beatles", 125.0)
    assert retrieved is not None
    assert retrieved.cached is True, "Retrieved result should have cached=True"


def test_cache_miss_returns_none(cache):
    """Test that cache miss returns None."""
    result = cache.get_cached("Nonexistent", "Nobody", 180.0)
    assert result is None, "Cache miss should return None"


def test_overwrite_existing_entry(cache, sample_sync_result):
    """Test that storing twice with same track overwrites the first entry."""
    # Store first result
    cache.store_result(sample_sync_result)

    # Create a modified result with different confidence
    modified_result = SyncResult(
        track=sample_sync_result.track,
        lines=sample_sync_result.lines,
        confidence=0.75,  # Different confidence
        timing_source="ctc_aligned",  # Different source
        processing_time_seconds=3.0,
    )

    # Store the modified result
    cache.store_result(modified_result)

    # Retrieve and verify the second result won
    retrieved = cache.get_cached("Yesterday", "The Beatles", 125.0)
    assert retrieved is not None
    assert retrieved.confidence == 0.75, "Should have updated confidence"
    assert retrieved.timing_source == "ctc_aligned", (
        "Should have updated timing_source"
    )


def test_get_by_id_returns_correct_result(cache, sample_sync_result):
    """Test that get_by_id returns the correct result."""
    cache.store_result(sample_sync_result)

    # Generate the track ID
    track_id = generate_track_id("Yesterday", "The Beatles", 125.0)

    # Retrieve by ID
    retrieved = cache.get_by_id(track_id)

    assert retrieved is not None, "Should retrieve result by ID"
    assert retrieved.track.title == sample_sync_result.track.title
    assert retrieved.confidence == sample_sync_result.confidence


def test_get_by_id_invalid_returns_none(cache):
    """Test that get_by_id with invalid ID returns None."""
    result = cache.get_by_id("invalid_track_id_12345")
    assert result is None, "Invalid track ID should return None"


def test_cache_key_includes_language():
    """Different language produces different track ID."""
    id_hi = generate_track_id("test", "artist", 100, "hi")
    id_none = generate_track_id("test", "artist", 100, None)
    assert id_hi != id_none, "Language should affect track ID"


def test_cache_isolation_by_language(cache, sample_sync_result):
    """Result stored with language='hi' is NOT found when looking up with language=None."""
    cache.store_result(sample_sync_result, language="hi")

    # Lookup without language should miss
    result = cache.get_cached("Yesterday", "The Beatles", 125.0, language=None)
    assert result is None, "Different language should produce cache miss"

    # Lookup with correct language should hit
    result = cache.get_cached("Yesterday", "The Beatles", 125.0, language="hi")
    assert result is not None, "Same language should produce cache hit"
