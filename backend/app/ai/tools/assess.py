"""`assess_complaint`: an advisory read on a complaint, plus duplicate lookup.

Every field in `AIAssessment` is a recommendation for a qualified QA reviewer,
never a confirmed root cause or a regulatory determination - the system
prompt (`app/ai/prompts/assess.py`) enforces the framing, and the schema's own
`disclaimer` field is never overridden here.

Duplicate detection is deliberately NOT an LLM call: it is a deterministic
database query over facts a reviewer can verify directly (batch number,
product, complaint type), so it costs nothing against the AI budget and never
needs to go through `app/ai/providers.py` at all.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import providers
from app.ai.prompts.assess import SYSTEM_PROMPT
from app.models.complaint import Complaint
from app.schemas.complaint import AIAssessment, DuplicateMatch


def assess_complaint(complaint: dict[str, Any]) -> AIAssessment:
    """A severity/priority recommendation, root-cause hypotheses and next
    steps for `complaint` (a JSON-mode complaint dict, e.g.
    `ComplaintRead(...).model_dump(mode="json")`)."""
    user_prompt = f"Complaint record (JSON):\n{_render(complaint)}"
    return providers.assess(
        system_prompt=SYSTEM_PROMPT, user_prompt=user_prompt, complaint=complaint
    )


def find_duplicate_candidates(
    db: Session, complaint: Complaint, limit: int = 5
) -> list[DuplicateMatch]:
    """Other complaints sharing enough facts with `complaint` to be worth a
    reviewer's second look. Exact-match heuristics only - see module docstring."""
    candidates: dict[int, DuplicateMatch] = {}

    def _merge(matches: list[Complaint], matched_on: list[str], similarity: float) -> None:
        for other in matches:
            if other.id == complaint.id:
                continue
            existing = candidates.get(other.id)
            if existing is not None:
                existing.matched_on = sorted(set(existing.matched_on) | set(matched_on))
                existing.similarity = max(existing.similarity, similarity)
                continue
            candidates[other.id] = DuplicateMatch(
                complaint_id=other.id,
                reference_code=other.reference_code,
                similarity=similarity,
                matched_on=list(matched_on),
                summary=((other.description or "")[:200] or None),
            )

    if complaint.batch_number:
        batch_matches = (
            db.execute(
                select(Complaint).where(
                    Complaint.id != complaint.id,
                    Complaint.batch_number.isnot(None),
                    Complaint.batch_number == complaint.batch_number,
                )
            )
            .scalars()
            .all()
        )
        _merge(list(batch_matches), ["batch_number"], 0.9)

    if complaint.product_name and complaint.complaint_type:
        type_matches = (
            db.execute(
                select(Complaint).where(
                    Complaint.id != complaint.id,
                    Complaint.product_name == complaint.product_name,
                    Complaint.complaint_type == complaint.complaint_type,
                )
            )
            .scalars()
            .all()
        )
        _merge(list(type_matches), ["product_name", "complaint_type"], 0.6)

    ranked = sorted(candidates.values(), key=lambda m: m.similarity, reverse=True)
    return ranked[:limit]


def _render(complaint: dict[str, Any]) -> str:
    return json.dumps(complaint, default=str)
