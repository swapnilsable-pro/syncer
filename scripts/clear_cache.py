#!/usr/bin/env python
"""One-time script to clear stale WhisperX-era cache entries."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from syncer.cache import CacheManager
from syncer.config import Settings

settings = Settings()
cache = CacheManager(settings.db_path)

before = len(cache.list_tracks())
print(f"Before: {before} cached entries")

cleared = cache.clear_all()
print(f"Cleared: {cleared} entries")

after = len(cache.list_tracks())
print(f"After: {after} cached entries")
assert after == 0, f"Expected 0 entries after clear, got {after}"
print("Cache cleared successfully.")
