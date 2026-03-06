"""Pytest configuration and shared fixtures."""

import pytest
from fastapi.testclient import TestClient

from syncer.api import app
from syncer.config import Settings
from syncer.pipeline import SyncPipeline


# NOTE: 'slow' and 'integration' markers are registered in pyproject.toml.
# No need to duplicate via pytest_configure here.


@pytest.fixture(scope="module")
def pipeline():
    """Initialize SyncPipeline once per test module (expensive — loads ML models)."""
    settings = Settings()
    return SyncPipeline(settings)


@pytest.fixture(scope="module")
def test_client():
    """FastAPI TestClient for API tests (triggers lifespan → loads real pipeline)."""
    return TestClient(app)
