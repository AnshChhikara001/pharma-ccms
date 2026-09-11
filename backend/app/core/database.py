"""Engine, session factory and the FastAPI session dependency.

One engine per process, one session per request. Endpoints never construct a
session themselves - they depend on `get_db`, which guarantees the session is
closed even when the handler raises.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

# SQLite (used by the test suite) needs check_same_thread disabled because
# FastAPI's TestClient runs requests on a different thread than the fixture.
_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}

engine = create_engine(
    settings.database_url,
    connect_args=_connect_args,
    pool_pre_ping=True,  # drop dead connections rather than erroring mid-request
    echo=False,
)

# expire_on_commit=False is load-bearing for the audit trail, not a
# performance tweak. With the default True, every commit expires the
# instance, so a later attribute change has no loaded "before" value and the
# trail silently records old=None. It also avoids DetachedInstanceError when
# an endpoint returns an ORM object after committing.
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    """Request-scoped session. Always closed, even on exception."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
