"""The complaint lifecycle.

Two kinds of test live here and both matter. The first asserts the transition
table *verbatim*: it is the written quality procedure expressed as code, and a
later edit that quietly permits "new -> closed" must fail the build rather than
ship. The second drives the table through HTTP, because a rule the engine
enforces and the endpoint forgets to call is no rule at all.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.audit import AuditEntry
from app.models.complaint import Complaint
from app.schemas.enums import AuditAction, ComplaintStatus, UserRole
from app.services import workflow

NEW = ComplaintStatus.NEW
UNDER_REVIEW = ComplaintStatus.UNDER_REVIEW
INVESTIGATION = ComplaintStatus.INVESTIGATION
ROOT_CAUSE = ComplaintStatus.ROOT_CAUSE_IDENTIFIED
CAPA_REQUIRED = ComplaintStatus.CAPA_REQUIRED
QA_REVIEW = ComplaintStatus.QA_REVIEW
CLOSED = ComplaintStatus.CLOSED


# ── The table itself ──────────────────────────────────────────────────────────


def test_transition_table_is_exactly_this() -> None:
    """Asserted verbatim. If this test needs changing, the quality procedure
    changed too, and that should be a conscious decision in review."""
    procedure = {
        NEW: frozenset({UNDER_REVIEW}),
        UNDER_REVIEW: frozenset({INVESTIGATION, QA_REVIEW}),
        INVESTIGATION: frozenset({ROOT_CAUSE, UNDER_REVIEW}),
        ROOT_CAUSE: frozenset({CAPA_REQUIRED, QA_REVIEW, INVESTIGATION}),
        CAPA_REQUIRED: frozenset({QA_REVIEW, INVESTIGATION}),
        QA_REVIEW: frozenset({CLOSED, INVESTIGATION}),
        CLOSED: frozenset(),
    }
    assert procedure == workflow.LEGAL_TRANSITIONS


def test_lifecycle_covers_every_status() -> None:
    """A status missing from LIFECYCLE would be unreachable and unorderable."""
    assert set(workflow.LIFECYCLE) == set(ComplaintStatus)
    assert set(workflow.LEGAL_TRANSITIONS) == set(ComplaintStatus)


def test_closed_is_the_only_terminal_status() -> None:
    terminal = {s for s in ComplaintStatus if workflow.is_terminal(s)}
    assert terminal == {CLOSED}


def test_every_status_is_reachable_from_new() -> None:
    """A stage nothing can reach is dead process. Walks the graph rather than
    trusting the table to look right."""
    seen = {NEW}
    frontier = [NEW]
    while frontier:
        for nxt in workflow.allowed_from(frontier.pop()):
            if nxt not in seen:
                seen.add(nxt)
                frontier.append(nxt)

    assert seen == set(ComplaintStatus)


def test_closing_is_the_only_move_needing_a_second_permission() -> None:
    from app.core.rbac import Permission

    extra = {
        status: workflow.permissions_for_target(status)
        for status in ComplaintStatus
        if len(workflow.permissions_for_target(status)) > 1
    }
    assert extra == {CLOSED: (Permission.WORKFLOW_TRANSITION, Permission.WORKFLOW_CLOSE)}


def test_only_backward_moves_require_a_reason() -> None:
    requiring = {
        (current, target)
        for current in ComplaintStatus
        for target in workflow.allowed_from(current)
        if workflow.requires_reason(current, target)
    }
    assert requiring == {
        (INVESTIGATION, UNDER_REVIEW),
        (ROOT_CAUSE, INVESTIGATION),
        (CAPA_REQUIRED, INVESTIGATION),
        (QA_REVIEW, INVESTIGATION),
    }


# ── Through the API ───────────────────────────────────────────────────────────


def test_forward_move_needs_no_reason(client: TestClient, auth_headers, make_complaint) -> None:
    complaint = make_complaint()

    response = client.post(
        f"/api/v1/complaints/{complaint['id']}/transition",
        json={"to_status": UNDER_REVIEW.value},
        headers=auth_headers(UserRole.COMPLAINT_OFFICER),
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "under_review"


def test_illegal_move_is_rejected_with_409(
    client: TestClient, auth_headers, make_complaint
) -> None:
    """Skipping the middle of the lifecycle is the mistake this guards."""
    complaint = make_complaint()

    response = client.post(
        f"/api/v1/complaints/{complaint['id']}/transition",
        json={"to_status": CLOSED.value},
        headers=auth_headers(UserRole.ADMIN),
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert "from 'new' to 'closed'" in detail
    assert "under_review" in detail  # tells the caller what *is* allowed


def test_backward_move_without_a_reason_is_422(
    client: TestClient, auth_headers, make_complaint, advance_to
) -> None:
    complaint = make_complaint()
    advance_to(complaint["id"], INVESTIGATION)

    response = client.post(
        f"/api/v1/complaints/{complaint['id']}/transition",
        json={"to_status": UNDER_REVIEW.value},
        headers=auth_headers(UserRole.ADMIN),
    )

    assert response.status_code == 422
    assert "requires a reason" in response.json()["detail"]


def test_blank_reason_does_not_count(
    client: TestClient, auth_headers, make_complaint, advance_to
) -> None:
    complaint = make_complaint()
    advance_to(complaint["id"], INVESTIGATION)

    response = client.post(
        f"/api/v1/complaints/{complaint['id']}/transition",
        json={"to_status": UNDER_REVIEW.value, "reason": "   "},
        headers=auth_headers(UserRole.ADMIN),
    )

    assert response.status_code == 422


def test_backward_move_with_a_reason_is_recorded(
    client: TestClient, auth_headers, make_complaint, advance_to
) -> None:
    complaint = make_complaint()
    advance_to(complaint["id"], INVESTIGATION)

    response = client.post(
        f"/api/v1/complaints/{complaint['id']}/transition",
        json={
            "to_status": UNDER_REVIEW.value,
            "reason": "Retained sample unavailable; returning for further evidence.",
        },
        headers=auth_headers(UserRole.ADMIN),
    )
    assert response.status_code == 200
    assert response.json()["status"] == "under_review"

    timeline = client.get(
        f"/api/v1/complaints/{complaint['id']}/transitions",
        headers=auth_headers(UserRole.VIEWER),
    ).json()
    assert timeline[-1]["reason"].startswith("Retained sample unavailable")
    assert timeline[-1]["from_status"] == "investigation"


def test_investigation_may_not_be_entered_unassigned(
    client: TestClient, auth_headers, make_complaint
) -> None:
    """An investigation with nobody responsible for it is how complaints age
    quietly past their due date."""
    complaint = make_complaint()
    headers = auth_headers(UserRole.ADMIN)
    client.post(
        f"/api/v1/complaints/{complaint['id']}/transition",
        json={"to_status": UNDER_REVIEW.value},
        headers=headers,
    )

    response = client.post(
        f"/api/v1/complaints/{complaint['id']}/transition",
        json={"to_status": INVESTIGATION.value},
        headers=headers,
    )

    assert response.status_code == 409
    assert "no investigator assigned" in response.json()["detail"]


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        (UserRole.QA_MANAGER, 200),
        (UserRole.ADMIN, 200),
        (UserRole.COMPLAINT_OFFICER, 403),
        (UserRole.INVESTIGATOR, 403),
        (UserRole.VIEWER, 403),
    ],
)
def test_only_qa_may_close(
    client: TestClient, auth_headers, make_complaint, advance_to, role: UserRole, expected: int
) -> None:
    """Closure is the one irreversible act, and the role matrix restricts it."""
    complaint = make_complaint()
    advance_to(complaint["id"], QA_REVIEW)

    response = client.post(
        f"/api/v1/complaints/{complaint['id']}/transition",
        json={"to_status": CLOSED.value},
        headers=auth_headers(role),
    )

    assert response.status_code == expected


def test_viewer_cannot_move_a_complaint_at_all(
    client: TestClient, auth_headers, make_complaint
) -> None:
    complaint = make_complaint()

    response = client.post(
        f"/api/v1/complaints/{complaint['id']}/transition",
        json={"to_status": UNDER_REVIEW.value},
        headers=auth_headers(UserRole.VIEWER),
    )

    assert response.status_code == 403
    assert "workflow:transition" in response.json()["detail"]


def test_closing_stamps_closed_at(
    client: TestClient, auth_headers, make_complaint, advance_to, db: Session
) -> None:
    complaint = make_complaint()
    advance_to(complaint["id"], CLOSED)

    stored = db.get(Complaint, complaint["id"])
    assert stored is not None
    assert stored.status is CLOSED
    assert stored.closed_at is not None


def test_a_closed_complaint_is_final(
    client: TestClient, auth_headers, make_complaint, advance_to
) -> None:
    """Reopening would rewrite a signed-off record. The regulated answer is a
    new complaint that references it."""
    complaint = make_complaint()
    advance_to(complaint["id"], CLOSED)

    response = client.post(
        f"/api/v1/complaints/{complaint['id']}/transition",
        json={"to_status": INVESTIGATION.value, "reason": "Customer disputes the outcome."},
        headers=auth_headers(UserRole.ADMIN),
    )

    assert response.status_code == 409
    assert "terminal status" in response.json()["detail"]


def test_transition_on_a_missing_complaint_is_404(client: TestClient, auth_headers) -> None:
    response = client.post(
        "/api/v1/complaints/9999/transition",
        json={"to_status": UNDER_REVIEW.value},
        headers=auth_headers(UserRole.ADMIN),
    )
    assert response.status_code == 404


# ── The timeline ──────────────────────────────────────────────────────────────


def test_timeline_starts_at_creation(client: TestClient, auth_headers, make_complaint) -> None:
    """Exactly one row per complaint has a null from_status: its arrival."""
    complaint = make_complaint()

    timeline = client.get(
        f"/api/v1/complaints/{complaint['id']}/transitions",
        headers=auth_headers(UserRole.VIEWER),
    ).json()

    assert len(timeline) == 1
    assert timeline[0]["from_status"] is None
    assert timeline[0]["to_status"] == "new"
    assert timeline[0]["changed_by_name"] == "Rahul Verma"  # the complaint officer


def test_timeline_records_every_hop_in_order(
    client: TestClient, auth_headers, make_complaint, advance_to
) -> None:
    complaint = make_complaint()
    advance_to(complaint["id"], CLOSED)

    timeline = client.get(
        f"/api/v1/complaints/{complaint['id']}/transitions",
        headers=auth_headers(UserRole.VIEWER),
    ).json()

    assert [row["to_status"] for row in timeline] == [
        "new",
        "under_review",
        "investigation",
        "root_cause_identified",
        "capa_required",
        "qa_review",
        "closed",
    ]


def test_a_transition_writes_a_status_changed_audit_entry(
    client: TestClient, auth_headers, make_complaint, db: Session
) -> None:
    """The audit trail is written by event listeners, not by the endpoint. This
    proves the endpoint does not have to remember."""
    complaint = make_complaint()
    client.post(
        f"/api/v1/complaints/{complaint['id']}/transition",
        json={"to_status": UNDER_REVIEW.value},
        headers=auth_headers(UserRole.QA_MANAGER),
    )

    entries = list(
        db.execute(
            select(AuditEntry).where(
                AuditEntry.entity_type == "Complaint",
                AuditEntry.entity_id == complaint["id"],
                AuditEntry.action == AuditAction.STATUS_CHANGED,
            )
        ).scalars()
    )

    assert len(entries) == 1
    assert entries[0].changes is not None
    assert entries[0].changes["status"] == {"old": "new", "new": "under_review"}
    assert entries[0].actor_email == "qa.manager@pharmaco.com"


# ── The table, as served to the frontend ──────────────────────────────────────


def test_workflow_endpoint_serves_the_enforced_table(client: TestClient) -> None:
    """The UI derives its buttons from this. If it could disagree with
    LEGAL_TRANSITIONS, the UI would offer moves the server rejects."""
    body = client.get("/api/v1/meta/workflow").json()

    served = {
        current: {option["to_status"] for option in options}
        for current, options in body["transitions"].items()
    }
    expected = {
        current.value: {target.value for target in targets}
        for current, targets in workflow.LEGAL_TRANSITIONS.items()
    }

    assert served == expected
    assert body["terminal_statuses"] == ["closed"]
    assert [s["value"] for s in body["lifecycle"]] == [s.value for s in workflow.LIFECYCLE]


def test_workflow_endpoint_marks_the_close_permission(client: TestClient) -> None:
    options = {
        o["to_status"]: o
        for o in client.get("/api/v1/meta/workflow").json()["transitions"]["qa_review"]
    }

    assert options["closed"]["required_permissions"] == ["workflow:close", "workflow:transition"]
    assert options["investigation"]["requires_reason"] is True
    assert options["investigation"]["is_backward"] is True
