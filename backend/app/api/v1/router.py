"""Aggregate router for API v1.

Each feature module registers its own APIRouter here. Phase 0 ships only the
meta endpoints; auth, complaints, workflow, ai and dashboard routers are added
in the phases that build them.
"""

from fastapi import APIRouter

from app.api.v1 import meta

api_router = APIRouter()
api_router.include_router(meta.router, prefix="/meta", tags=["meta"])
