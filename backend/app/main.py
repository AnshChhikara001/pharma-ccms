"""FastAPI application entrypoint.

Kept deliberately thin: it wires middleware and mounts the versioned router, and
nothing else. Business logic lives in app/services, data access in app/models.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.middleware import AuditContextMiddleware
from app.services.audit import install_audit_listeners

settings = get_settings()

# Attach the audit-trail listeners before any session exists, so no mutation
# can ever occur outside their view.
install_audit_listeners()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description=(
        "Pharmaceutical customer complaint management with AI-assisted intake, "
        "triage and investigation support."
    ),
    openapi_url=f"{settings.api_v1_prefix}/openapi.json",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Order matters: middleware added last runs first. AuditContextMiddleware must
# wrap the request before any handler opens a database session.
app.add_middleware(AuditContextMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/health", tags=["system"], summary="Liveness probe")
def health() -> dict[str, str]:
    """Unauthenticated liveness check used by Docker, CI and the smoke tests."""
    return {"status": "ok", "environment": settings.environment}
