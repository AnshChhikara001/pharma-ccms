"""Aggregate router for API v1.

Each feature module registers its own APIRouter here. Complaints, workflow, ai
and dashboard routers arrive in the phases that build them.
"""

from fastapi import APIRouter

from app.api.v1 import auth, meta

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(meta.router, prefix="/meta", tags=["meta"])
