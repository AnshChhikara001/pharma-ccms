"""FastAPI application entrypoint.

Kept deliberately thin: it wires middleware and mounts the versioned router, and
nothing else. Business logic lives in app/services, data access in app/models.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings

settings = get_settings()

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
