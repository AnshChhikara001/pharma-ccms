"""Aggregate router for API v1.

Each feature module registers its own APIRouter here. The dashboard router
arrives in the phase that builds it.
"""

from fastapi import APIRouter

from app.api.v1 import ai, auth, complaints, meta

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(meta.router, prefix="/meta", tags=["meta"])
api_router.include_router(complaints.router, prefix="/complaints", tags=["complaints"])
api_router.include_router(ai.router, prefix="/ai", tags=["ai"])
