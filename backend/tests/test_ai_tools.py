"""The three AI tools, exercised against the mock adapter (the only provider
this suite is ever allowed to reach - see `tests/conftest.py`).

`test_edit_changes_only_the_fields_the_instruction_mentions` and
`test_edit_endpoint_round_trip_is_non_destructive` are the dedicated
regression tests CLAUDE.md and `app/ai/tools/edit.py` call for: an
instruction must change exactly the fields it addresses and nothing else,
end to end, from the raw instruction text through to a persisted complaint.
Do not weaken either of them.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.ai.graph import run_assess, run_edit, run_extract
from app.ai.tools.assess import assess_complaint, find_duplicate_candidates
from app.ai.tools.edit import edit_complaint
from app.ai.tools.extract import extract_complaint
from app.models.complaint import Complaint
from app.schemas.ai import ComplaintFieldChanges
from app.schemas.complaint import ComplaintUpdate
from app.schemas.enums import UserRole
from tests.fixtures.complaint_texts import EDIT_CASES, EXTRACTION_CASES


def test_complaint_field_changes_mirrors_complaint_update() -> None:
    """`ComplaintFieldChanges` (app/schemas/ai.py) exists only because
    `ComplaintUpdate` cannot appear in a response body without FastAPI
    generating split Input/Output OpenAPI schemas for it - see that class's
    docstring. Its field set must track `ComplaintUpdate`'s exactly, or the
    `/complaints/{id}/edit` response silently stops describing a field
    `ComplaintUpdate` (and therefore `PATCH /api/v1/complaints/{id}`) has."""
    assert set(ComplaintFieldChanges.model_fields) == set(ComplaintUpdate.model_fields)


def _as_str_dict(fields: dict[str, Any]) -> dict[str, str]:
    """`ComplaintUpdate.model_dump(exclude_unset=True)` mixes plain strings,
    `Decimal` and `StrEnum` members - all of which stringify to the same text
    the fixtures were written against, so comparing as strings sidesteps
    type-specific equality quirks (`Decimal('48') != '48'`, for instance)."""
    return {k: str(v) for k, v in fields.items()}


# ── extract_complaint ────────────────────────────────────────────────────────


@pytest.mark.parametrize("case", EXTRACTION_CASES, ids=lambda c: c.name)
def test_extract_complaint_matches_fixture(case) -> None:
    result = extract_complaint(case.text)

    actual = _as_str_dict(result.fields.model_dump(exclude_unset=True))
    assert actual == case.expected_fields
    assert sorted(result.missing_fields) == sorted(case.expected_missing)


def test_extract_complaint_provenance_covers_every_populated_field() -> None:
    """Every field the tool reports must carry a provenance entry - that is
    what drives the "AI populated this" highlighting in the intake UI."""
    case = EXTRACTION_CASES[0]
    result = extract_complaint(case.text)

    provenance_fields = {p.field for p in result.provenance}
    populated_fields = set(result.fields.model_dump(exclude_unset=True))
    assert provenance_fields == populated_fields
    for entry in result.provenance:
        assert entry.source_excerpt  # a verbatim excerpt, not a bare claim
        assert entry.confidence is not None


def test_extract_complaint_missing_fields_drive_clarifying_questions() -> None:
    vague = next(c for c in EXTRACTION_CASES if c.name == "vague_report_nothing_extractable")
    result = extract_complaint(vague.text)

    assert result.missing_fields
    assert result.clarifying_questions
    assert len(result.clarifying_questions) <= 5  # ExtractedComplaint's own cap
    assert result.extraction_notes  # the tool says *something* when it found nothing


def test_extract_complaint_never_states_severity_or_priority() -> None:
    """Extraction reports facts from the text; severity/priority is
    `assess_complaint`'s job, not this tool's - see app/ai/prompts/extract.py."""
    case = next(c for c in EXTRACTION_CASES if c.name == "discoloration_hospital_all_fields")
    result = extract_complaint(case.text)

    assert "severity" not in result.fields.model_fields_set
    assert "priority" not in result.fields.model_fields_set


# ── edit_complaint: the non-destructive regression tests ───────────────────


_EXISTING_COMPLAINT: dict[str, Any] = {
    "id": 42,
    "reference_code": "CMP-2026-0042",
    "status": "under_review",
    "source": "email",
    "customer_name": "Original Customer",
    "customer_contact": "original@example.com",
    "reporter_name": "Original Reporter",
    "product_name": "Original Product",
    "product_strength": "250 mg",
    "dosage_form": "capsule",
    "batch_number": "OLD-000",
    "manufacturing_date": "2025-01-01",
    "expiry_date": "2027-01-01",
    "quantity_affected": "10",
    "quantity_unit": "capsules",
    "complaint_type": "foreign_matter",
    "complaint_date": "2026-01-01",
    "description": "Original description text that must survive the edit untouched.",
    "severity": "major",
    "priority": "high",
    "assigned_investigator_id": None,
    "due_date": "2026-02-01",
    "created_at": "2026-01-01T00:00:00+00:00",
    "updated_at": "2026-01-01T00:00:00+00:00",
    "created_by_id": 1,
    "is_overdue": False,
}


@pytest.mark.parametrize("case", EDIT_CASES, ids=lambda c: c.name)
def test_edit_changes_only_the_fields_the_instruction_mentions(case) -> None:
    """THE regression test. `_EXISTING_COMPLAINT` has every field populated;
    an instruction that addresses only some of them must leave the rest
    genuinely *unset* on the returned `ComplaintUpdate` - not null, absent -
    so a caller serialising with `exclude_unset=True` (as every caller in
    this codebase must, per CLAUDE.md) touches nothing else."""
    update, provenance = edit_complaint(_EXISTING_COMPLAINT, case.instruction)

    assert update.model_fields_set == set(case.expected_changes)

    changed = _as_str_dict(update.model_dump(exclude_unset=True))
    assert changed == case.expected_changes

    assert {p.field for p in provenance} == set(case.expected_changes)


def test_edit_complaint_batch_and_quantity_case_leaves_everything_else_unset() -> None:
    """Restated explicitly against the exact CLAUDE.md example, independent
    of the fixture table, so this specific guarantee cannot silently drift
    even if the fixture corpus is later edited."""
    instruction = "The batch number is BMX 240602 and affected quantity is 48 capsules."
    update, _ = edit_complaint(_EXISTING_COMPLAINT, instruction)

    assert update.batch_number == "BMX 240602"
    assert update.quantity_affected == 48
    assert update.quantity_unit == "capsules"

    untouched = set(update.model_fields.keys()) - {
        "batch_number",
        "quantity_affected",
        "quantity_unit",
    }
    for field_name in untouched:
        assert field_name not in update.model_fields_set, (
            f"'{field_name}' must stay unset - the instruction never mentioned it"
        )


def test_edit_complaint_via_graph_matches_direct_tool_call() -> None:
    """`app.ai.graph.run_edit` must produce the same result as calling the
    tool directly - the graph is routing, not re-implementing the logic."""
    instruction = "Update the customer name to Riverside Community Pharmacy."
    direct_update, direct_prov = edit_complaint(_EXISTING_COMPLAINT, instruction)
    graph_update, graph_prov = run_edit(_EXISTING_COMPLAINT, instruction)

    assert direct_update.model_dump(exclude_unset=True) == graph_update.model_dump(
        exclude_unset=True
    )
    assert {p.field for p in direct_prov} == {p.field for p in graph_prov}


# ── edit_complaint: end-to-end through the API + the existing PATCH endpoint ─


def test_edit_endpoint_round_trip_is_non_destructive(
    client: TestClient, auth_headers, make_complaint
) -> None:
    """The full path a real client takes: propose via `POST .../edit`, then
    apply the proposal through the existing, already-guarded
    `PATCH /api/v1/complaints/{id}`. Every field not named in the instruction
    must come back byte-identical to what it was before the edit."""
    complaint = make_complaint(
        severity="major",
        priority="high",
        batch_number="OLD-000",
        product_name="Original Product",
        customer_name="Original Customer",
    )
    headers = auth_headers(UserRole.COMPLAINT_OFFICER)

    propose = client.post(
        f"/api/v1/ai/complaints/{complaint['id']}/edit",
        json={
            "instruction": "The batch number is BMX 240602 and affected quantity is 48 capsules."
        },
        headers=headers,
    )
    assert propose.status_code == 200, propose.text
    proposed = propose.json()

    # response_model_exclude_unset must have stripped the untouched fields
    # off the wire - not just left them null - see app/api/v1/ai.py.
    assert set(proposed["update"].keys()) == {"batch_number", "quantity_affected", "quantity_unit"}

    apply_response = client.patch(
        f"/api/v1/complaints/{complaint['id']}",
        json=proposed["update"],
        headers=headers,
    )
    assert apply_response.status_code == 200, apply_response.text
    updated = apply_response.json()

    assert updated["batch_number"] == "BMX 240602"
    assert float(updated["quantity_affected"]) == 48
    assert updated["quantity_unit"] == "capsules"

    # Everything the instruction did not mention must be untouched.
    for field_name in ("severity", "priority", "product_name", "customer_name", "description"):
        assert updated[field_name] == complaint[field_name], field_name


# ── assess_complaint ─────────────────────────────────────────────────────────


def test_assess_complaint_always_carries_the_disclaimer() -> None:
    result = assess_complaint({"complaint_type": "foreign_matter", "batch_number": "BMX-1"})
    assert "recommendation" in result.disclaimer.lower()
    assert "qualified" in result.disclaimer.lower()


def test_assess_complaint_recommends_higher_severity_for_adverse_events() -> None:
    critical = assess_complaint({"complaint_type": "adverse_event", "batch_number": "BMX-1"})
    minor = assess_complaint({"complaint_type": "broken_or_chipped", "batch_number": "BMX-1"})

    assert critical.recommended_severity == "critical"
    assert critical.recommended_priority == "urgent"
    assert minor.recommended_severity == "minor"


def test_assess_complaint_root_causes_are_framed_as_hypotheses() -> None:
    """CLAUDE.md non-negotiable #4: never a confirmed determination."""
    result = assess_complaint({"complaint_type": "foreign_matter", "batch_number": "BMX-1"})
    assert result.potential_root_causes
    for cause in result.potential_root_causes:
        lowered = cause.lower()
        assert "confirmed" not in lowered
        assert "established" not in lowered


def test_assess_complaint_completeness_score_reflects_populated_fields() -> None:
    sparse = assess_complaint({"complaint_type": "other"})
    full = assess_complaint(
        {
            "complaint_type": "other",
            "product_name": "X",
            "batch_number": "Y",
            "quantity_affected": 1,
            "quantity_unit": "units",
            "customer_name": "Z",
            "description": "d",
            "complaint_date": "2026-01-01",
        }
    )
    assert full.completeness_score > sparse.completeness_score
    assert full.completeness_score == 100


def test_assess_complaint_via_graph_matches_direct_tool_call() -> None:
    complaint = {"complaint_type": "adverse_event", "batch_number": "BMX-1"}
    assert assess_complaint(complaint).model_dump() == run_assess(complaint).model_dump()


def test_extract_complaint_via_graph_matches_direct_tool_call() -> None:
    case = EXTRACTION_CASES[0]
    assert extract_complaint(case.text).model_dump() == run_extract(case.text).model_dump()


# ── find_duplicate_candidates ────────────────────────────────────────────────


def test_find_duplicate_candidates_matches_on_batch_number(
    client: TestClient, auth_headers, make_complaint, db
) -> None:
    first = make_complaint(batch_number="DUPE-0001", product_name="Amoxicillin")
    second = make_complaint(batch_number="DUPE-0001", product_name="Amoxicillin")
    unrelated = make_complaint(batch_number="UNRELATED-9999")

    target = db.get(Complaint, first["id"])
    duplicates = find_duplicate_candidates(db, target)

    ids = {d.complaint_id for d in duplicates}
    assert second["id"] in ids
    assert unrelated["id"] not in ids
    match = next(d for d in duplicates if d.complaint_id == second["id"])
    assert "batch_number" in match.matched_on
    assert match.reference_code == second["reference_code"]


def test_find_duplicate_candidates_excludes_the_complaint_itself(
    client: TestClient, auth_headers, make_complaint, db
) -> None:
    complaint = make_complaint(batch_number="SOLO-0001")
    target = db.get(Complaint, complaint["id"])

    duplicates = find_duplicate_candidates(db, target)
    assert all(d.complaint_id != complaint["id"] for d in duplicates)


# ── router permissions ───────────────────────────────────────────────────────


def test_get_budget_requires_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/ai/budget")
    assert response.status_code == 401


def test_get_budget_ok_for_any_authenticated_role(client: TestClient, auth_headers) -> None:
    response = client.get("/api/v1/ai/budget", headers=auth_headers(UserRole.VIEWER))
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "mock"
    assert "budget_usd" in body and "spent_usd" in body and "remaining_usd" in body


def test_extract_endpoint_forbidden_without_ai_extract_permission(
    client: TestClient, auth_headers
) -> None:
    response = client.post(
        "/api/v1/ai/extract",
        json={"text": "Some complaint text."},
        headers=auth_headers(UserRole.VIEWER),
    )
    assert response.status_code == 403


def test_extract_endpoint_ok_for_complaint_officer(client: TestClient, auth_headers) -> None:
    case = EXTRACTION_CASES[0]
    response = client.post(
        "/api/v1/ai/extract",
        json={"text": case.text},
        headers=auth_headers(UserRole.COMPLAINT_OFFICER),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["fields"]["batch_number"] == "BMX 240602"


def test_assess_endpoint_forbidden_for_viewer(
    client: TestClient, auth_headers, make_complaint
) -> None:
    complaint = make_complaint()
    response = client.post(
        f"/api/v1/ai/complaints/{complaint['id']}/assess",
        headers=auth_headers(UserRole.VIEWER),
    )
    assert response.status_code == 403


def test_assess_endpoint_persists_an_ai_assessment_record(
    client: TestClient, auth_headers, make_complaint, db
) -> None:
    complaint = make_complaint(
        complaint_type="adverse_event", description="Patient reported a severe reaction."
    )
    response = client.post(
        f"/api/v1/ai/complaints/{complaint['id']}/assess",
        headers=auth_headers(UserRole.QA_MANAGER),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["assessment"]["disclaimer"]
    assert "duplicates" in body

    from app.models.complaint import AIAssessmentRecord

    records = (
        db.query(AIAssessmentRecord)
        .filter(AIAssessmentRecord.complaint_id == complaint["id"])
        .all()
    )
    assert len(records) == 1
    assert records[0].is_superseded is False
    assert records[0].provider == "mock"


def test_assess_endpoint_supersedes_prior_assessment(
    client: TestClient, auth_headers, make_complaint, db
) -> None:
    complaint = make_complaint(complaint_type="foreign_matter")
    headers = auth_headers(UserRole.QA_MANAGER)

    first = client.post(f"/api/v1/ai/complaints/{complaint['id']}/assess", headers=headers)
    second = client.post(f"/api/v1/ai/complaints/{complaint['id']}/assess", headers=headers)
    assert first.status_code == 200
    assert second.status_code == 200

    from app.models.complaint import AIAssessmentRecord

    records = (
        db.query(AIAssessmentRecord)
        .filter(AIAssessmentRecord.complaint_id == complaint["id"])
        .order_by(AIAssessmentRecord.id)
        .all()
    )
    assert len(records) == 2
    assert records[0].is_superseded is True
    assert records[1].is_superseded is False


def test_assessment_read_returns_404_before_generation(
    client: TestClient, auth_headers, make_complaint
) -> None:
    complaint = make_complaint()

    response = client.get(
        f"/api/v1/ai/complaints/{complaint['id']}/assessment",
        headers=auth_headers(UserRole.VIEWER),
    )

    assert response.status_code == 404
    assert "No AI assessment exists" in response.json()["detail"]


def test_assessment_read_is_available_to_viewers_without_spending_again(
    client: TestClient, auth_headers, make_complaint
) -> None:
    complaint = make_complaint(complaint_type="adverse_event", batch_number="READ-0001")
    qa_headers = auth_headers(UserRole.QA_MANAGER)

    generated = client.post(
        f"/api/v1/ai/complaints/{complaint['id']}/assess",
        headers=qa_headers,
    )
    assert generated.status_code == 200, generated.text

    read = client.get(
        f"/api/v1/ai/complaints/{complaint['id']}/assessment",
        headers=auth_headers(UserRole.VIEWER),
    )

    assert read.status_code == 200, read.text
    body = read.json()
    assert body["assessment"]["recommended_severity"] == "critical"
    assert body["duplicates"] == []
