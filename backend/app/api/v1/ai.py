"""AI endpoints: extraction, guided edits and advisory assessment.

Every call here goes through `app/ai/graph.py`, which enforces an explicit
`recursion_limit`, and every provider call inside it goes through
`app/ai/budget.py`, which enforces the spend cap *before* any provider is
contacted. A `BudgetExceeded` raised there surfaces here as 402 Payment
Required - the closest standard status to "this would cost money there is no
budget left to spend."

Handlers stay thin, same convention as `complaints.py`: resolve the complaint
or 404, check the permission the request needs, translate domain errors to
status codes, and leave the actual work to `app/ai/*`.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.ai import budget, graph
from app.ai.tools.assess import find_duplicate_candidates
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.deps import get_current_user, require
from app.core.rbac import Permission
from app.models.complaint import AIAssessmentRecord, Complaint
from app.models.user import User
from app.schemas.ai import (
    AssessResponse,
    BudgetStatusResponse,
    ComplaintFieldChanges,
    EditRequest,
    EditResponse,
    ExtractRequest,
)
from app.schemas.complaint import AIAssessment, ComplaintRead, ExtractedComplaint

router = APIRouter()


def _get_or_404(db: Session, complaint_id: int) -> Complaint:
    complaint = db.get(Complaint, complaint_id)
    if complaint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Complaint {complaint_id} not found",
        )
    return complaint


def _model_label(settings: Settings) -> str:
    if settings.ai_provider == "gemini":
        return settings.gemini_model
    if settings.ai_provider == "openai":
        return settings.openai_model
    return "mock"


@router.get("/budget", response_model=BudgetStatusResponse, summary="Current AI spend")
def get_budget(_: User = Depends(get_current_user)) -> BudgetStatusResponse:
    """Spend so far against `settings.ai_budget_usd`. Any authenticated user
    may read this - it drives the always-visible spend indicator on every AI
    panel, not just the ones an individual role can trigger."""
    spend = budget.get_status()
    return BudgetStatusResponse(
        provider=spend.provider,
        budget_usd=spend.budget_usd,
        spent_usd=spend.spent_usd,
        remaining_usd=spend.remaining_usd,
        call_count=spend.call_count,
        updated_at=spend.updated_at,
    )


@router.post(
    "/extract", response_model=ExtractedComplaint, summary="Extract fields from complaint text"
)
def extract(
    payload: ExtractRequest,
    _: User = Depends(require(Permission.AI_EXTRACT)),
) -> ExtractedComplaint:
    """Structured extraction for the intake screen. No complaint needs to
    exist yet - this is what turns a pasted email or transcript into a
    pre-filled intake form. See `app/ai/tools/extract.py`."""
    try:
        return graph.run_extract(payload.text)
    except budget.BudgetExceeded as exc:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=str(exc)) from exc


@router.get(
    "/complaints/{complaint_id}/assessment",
    response_model=AssessResponse,
    summary="Get the latest saved assessment",
)
def get_assessment(
    complaint_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require(Permission.COMPLAINT_READ)),
) -> AssessResponse:
    """Read the latest assessment without spending AI budget.

    Assessments are append-only records because the recommendation can change as
    a complaint is completed. The detail page needs a read path so refreshing
    the page does not re-run the model, while duplicate candidates are safely
    recomputed from current database facts because that query is deterministic.
    """
    complaint = _get_or_404(db, complaint_id)
    record = db.execute(
        select(AIAssessmentRecord)
        .where(
            AIAssessmentRecord.complaint_id == complaint.id,
            AIAssessmentRecord.is_superseded.is_(False),
        )
        .order_by(AIAssessmentRecord.created_at.desc(), AIAssessmentRecord.id.desc())
        .limit(1)
    ).scalar_one_or_none()

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No AI assessment exists for complaint {complaint.reference_code}",
        )

    return AssessResponse(
        assessment=AIAssessment.model_validate(record.payload),
        duplicates=find_duplicate_candidates(db, complaint),
    )


@router.post(
    "/complaints/{complaint_id}/edit",
    response_model=EditResponse,
    # Load-bearing, not a nicety: `response_model_exclude_unset` recurses into
    # the nested `update: ComplaintFieldChanges` and drops every field that
    # instance never had set - not just ones equal to None. Without it,
    # FastAPI would serialise all 18 fields with the untouched ones as
    # explicit JSON nulls, and a client that relayed that object straight into
    # `PATCH /api/v1/complaints/{id}` (which reads exclude_unset off the
    # *wire* JSON, not off any Python state) would wipe every field the
    # instruction never mentioned - exactly the failure this whole feature
    # exists to prevent.
    response_model_exclude_unset=True,
    summary="Propose a partial edit from an instruction",
)
def edit(
    complaint_id: int,
    payload: EditRequest,
    db: Session = Depends(get_db),
    _: User = Depends(require(Permission.AI_EXTRACT)),
) -> EditResponse:
    """Propose only the fields `payload.instruction` asks to change.

    Returns a preview, never an applied change - the AI layer is advisory
    (CLAUDE.md non-negotiable #4). A caller who accepts the proposal submits
    `update` verbatim to the existing `PATCH /api/v1/complaints/{id}`, which
    already enforces `exclude_unset=True`, RBAC and the merge-validation
    rules; this endpoint does not touch the database.

    The proposal is carried as `ComplaintFieldChanges`, not `ComplaintUpdate`
    itself - see that class's docstring in `app/schemas/ai.py` for why
    `ComplaintUpdate` must never appear in a response body.
    """
    complaint = _get_or_404(db, complaint_id)
    existing = ComplaintRead.model_validate(complaint).model_dump(mode="json")
    try:
        proposed_update, provenance = graph.run_edit(existing, payload.instruction)
    except budget.BudgetExceeded as exc:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=str(exc)) from exc

    # Only the fields the tool actually set are passed through - constructing
    # `ComplaintFieldChanges` from the full instance (e.g. via
    # `from_attributes`) would read every attribute via getattr and mark all
    # 18 as "set", silently defeating `response_model_exclude_unset` above.
    changes = proposed_update.model_dump(exclude_unset=True)
    return EditResponse(update=ComplaintFieldChanges(**changes), provenance=provenance)


@router.post(
    "/complaints/{complaint_id}/assess",
    response_model=AssessResponse,
    summary="Advisory assessment and duplicate check",
)
def assess(
    complaint_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require(Permission.AI_ASSESS)),
) -> AssessResponse:
    """An advisory severity/priority recommendation, plus duplicate
    candidates found by `find_duplicate_candidates`.

    The assessment is persisted as an `AIAssessmentRecord` - an append-only
    history per that model's own docstring - with any prior record for this
    complaint marked superseded rather than deleted, so the trail shows what
    the AI advised *at the time* a decision was made. The audit trail then
    writes itself from that insert, same as everywhere else in this codebase.

    Per-call token/cost attribution on the stored record is a known
    simplification for this phase: `app/ai/budget.py`'s ledger already
    tracks aggregate spend precisely (what the hard cap actually needs), and
    threading exact per-call usage through `graph.run_assess` into this
    record is left for a later phase rather than widening every layer's
    return signature for a column no endpoint reads yet.
    """
    complaint = _get_or_404(db, complaint_id)
    complaint_data = ComplaintRead.model_validate(complaint).model_dump(mode="json")

    try:
        assessment = graph.run_assess(complaint_data)
    except budget.BudgetExceeded as exc:
        raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=str(exc)) from exc

    duplicates = find_duplicate_candidates(db, complaint)

    settings = get_settings()
    db.execute(
        update(AIAssessmentRecord)
        .where(
            AIAssessmentRecord.complaint_id == complaint.id,
            AIAssessmentRecord.is_superseded.is_(False),
        )
        .values(is_superseded=True)
    )
    db.add(
        AIAssessmentRecord(
            complaint_id=complaint.id,
            payload=assessment.model_dump(mode="json"),
            provider=settings.ai_provider,
            model=_model_label(settings),
            is_superseded=False,
        )
    )
    db.commit()

    return AssessResponse(assessment=assessment, duplicates=duplicates)
