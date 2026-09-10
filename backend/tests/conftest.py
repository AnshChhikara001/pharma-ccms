"""Shared pytest fixtures.

The environment is pinned BEFORE `app` is imported anywhere. Settings are cached
via lru_cache, so if the app were imported first these values would be baked in
too late and the suite could reach a live provider. Import order is the whole
safety mechanism here - do not move these lines below the app imports.
"""

import os

os.environ["AI_PROVIDER"] = "mock"
os.environ["ENVIRONMENT"] = "test"
os.environ["SECRET_KEY"] = "test-secret-key-not-used-outside-the-suite"
# In-memory SQLite keeps unit tests independent of a running Postgres.
os.environ["DATABASE_URL_OVERRIDE"] = "sqlite+pysqlite:///:memory:"

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.main import app


@pytest.fixture(scope="session", autouse=True)
def _assert_never_live() -> None:
    """Fail the entire suite loudly if it is somehow configured to spend money."""
    settings = get_settings()
    assert settings.ai_provider == "mock", (
        f"Test suite must run against the mock AI provider, got "
        f"'{settings.ai_provider}'. Live providers cost money and make tests flaky."
    )


@pytest.fixture
def client() -> TestClient:
    """Synchronous API client bound to the app."""
    return TestClient(app)
