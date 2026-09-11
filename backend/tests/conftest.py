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
# File-backed SQLite rather than :memory: - the app's engine and the test's
# session must see the same database, and an in-memory database is private to
# its connection.
os.environ["DATABASE_URL_OVERRIDE"] = "sqlite+pysqlite:///./test_ccms.db"

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal, engine
from app.main import app
from app.models import Base, User
from app.schemas.enums import UserRole
from seeds.users import DEMO_PASSWORD, seed_users

TEST_DB_PATH = Path("./test_ccms.db")


@pytest.fixture(scope="session", autouse=True)
def _assert_never_live() -> None:
    """Fail the entire suite loudly if it is somehow configured to spend money."""
    settings = get_settings()
    assert settings.ai_provider == "mock", (
        f"Test suite must run against the mock AI provider, got "
        f"'{settings.ai_provider}'. Live providers cost money and make tests flaky."
    )


@pytest.fixture(autouse=True)
def _fresh_schema() -> Generator[None, None, None]:
    """Rebuild the schema around every test.

    Complete isolation costs a few milliseconds on SQLite and removes an entire
    class of order-dependent failures, where one test's leftover row changes
    another's result.
    """
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(scope="session", autouse=True)
def _remove_db_file() -> Generator[None, None, None]:
    yield
    TEST_DB_PATH.unlink(missing_ok=True)


@pytest.fixture
def db() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def users(db: Session) -> dict[UserRole, User]:
    """One seeded user per role, keyed by role."""
    return {user.role: user for user in seed_users(db)}


@pytest.fixture
def token_for(client: TestClient, users: dict[UserRole, User]):
    """Return a callable that logs in as a given role and yields its token."""

    def _login(role: UserRole) -> str:
        response = client.post(
            "/api/v1/auth/login/json",
            json={"email": users[role].email, "password": DEMO_PASSWORD},
        )
        assert response.status_code == 200, response.text
        return str(response.json()["access_token"])

    return _login


@pytest.fixture
def auth_headers(token_for):
    """Return a callable producing Authorization headers for a role."""

    def _headers(role: UserRole) -> dict[str, str]:
        return {"Authorization": f"Bearer {token_for(role)}"}

    return _headers
