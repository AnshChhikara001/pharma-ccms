"""Request/response envelopes for `POST/GET /api/v1/ai/*`.

These are thin wire shapes for the AI endpoints only - they compose the
schemas in `app/schemas/complaint.py` rather than redefining any complaint
field. `ComplaintFieldChanges` is defined in `app/schemas/complaint.py`,
alongside `ComplaintUpdate` which it mirrors, and re-exported here.
The complaint shape itself is still defined exactly once, in
`app/schemas/complaint.py`.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.complaint import (
    AIAssessment,
    ComplaintFieldChanges,
    DuplicateMatch,
    FieldProvenance,
)

__all__ = [
    "AssessResponse",
    "BudgetStatusResponse",
    "ComplaintFieldChanges",
    "EditRequest",
    "EditResponse",
    "ExtractRequest",
]


class ExtractRequest(BaseModel):
    """Raw complaint text to extract structured fields from."""

    text: str = Field(..., min_length=1, max_length=8000)


class EditRequest(BaseModel):
    """A natural-language instruction describing what should change."""

    instruction: str = Field(..., min_length=1, max_length=2000)


class EditResponse(BaseModel):
    """The proposed change, for a reviewer to apply.

    Deliberately a preview, not an applied update: the AI layer is advisory
    (CLAUDE.md non-negotiable #4), so this endpoint never writes to the
    complaint itself. A caller who accepts the proposal submits `update`
    verbatim to the existing `PATCH /api/v1/complaints/{id}`, which already
    enforces `exclude_unset=True`, RBAC and the merge-validation rules.
    """

    update: ComplaintFieldChanges
    provenance: list[FieldProvenance]


class AssessResponse(BaseModel):
    """An advisory assessment plus any duplicate candidates found for it."""

    assessment: AIAssessment
    duplicates: list[DuplicateMatch]


class BudgetStatusResponse(BaseModel):
    """Current AI spend against the configured cap."""

    provider: str
    budget_usd: Decimal
    spent_usd: Decimal
    remaining_usd: Decimal
    call_count: int
    updated_at: str | None = Field(None, description="ISO timestamp of the last recorded call.")
