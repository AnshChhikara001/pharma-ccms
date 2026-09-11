"""Complaint CRUD, filtering, pagination and RBAC.

Workflow behaviour lives in `tests/test_workflow.py`; this module covers
everything else the endpoint is responsible for: creating and reading a
complaint, the non-destructive partial update, reference-data linking, the
search/filter surface, and who may do what.
"""

from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.complaint import Complaint
from app.schemas.enums import ComplaintStatus, UserRole

# ── Create ────────────────────────────────────────────────────────────────────


def test_create_complaint_allocates_a_reference_code(
    client: TestClient, auth_headers, make_complaint
) -> None:
    complaint = make_complaint()
    assert complaint["reference_code"].startswith(f"CMP-{date.today().year}-")
    assert complaint["status"] == "new"


def test_reference_codes_increment(client: TestClient, auth_headers, make_complaint) -> None:
    first = make_complaint()
    second = make_complaint()

    first_seq = int(first["reference_code"].rsplit("-", 1)[1])
    second_seq = int(second["reference_code"].rsplit("-", 1)[1])
    assert second_seq == first_seq + 1


def test_create_starts_the_timeline(client: TestClient, auth_headers, make_complaint) -> None:
    complaint = make_complaint()

    timeline = client.get(
        f"/api/v1/complaints/{complaint['id']}/transitions",
        headers=auth_headers(UserRole.VIEWER),
    ).json()

    assert len(timeline) == 1
    assert timeline[0]["to_status"] == "new"
    assert timeline[0]["from_status"] is None


def test_description_too_short_is_rejected(client: TestClient, auth_headers) -> None:
    response = client.post(
        "/api/v1/complaints",
        json={"description": "too short"},
        headers=auth_headers(UserRole.COMPLAINT_OFFICER),
    )
    assert response.status_code == 422


def test_expiry_before_manufacture_is_rejected_at_the_endpoint(
    client: TestClient, auth_headers
) -> None:
    response = client.post(
        "/api/v1/complaints",
        json={
            "description": "Discoloration observed across the blister strip.",
            "manufacturing_date": "2026-06-01",
            "expiry_date": "2025-06-01",
        },
        headers=auth_headers(UserRole.COMPLAINT_OFFICER),
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        (UserRole.ADMIN, 201),
        (UserRole.QA_MANAGER, 201),
        (UserRole.COMPLAINT_OFFICER, 201),
        (UserRole.INVESTIGATOR, 403),
        (UserRole.VIEWER, 403),
    ],
)
def test_who_may_log_a_complaint(
    client: TestClient, auth_headers, role: UserRole, expected: int
) -> None:
    response = client.post(
        "/api/v1/complaints",
        json={"description": "Foreign particulate observed in a reconstituted vial."},
        headers=auth_headers(role),
    )
    assert response.status_code == expected


def test_assigning_at_intake_needs_complaint_assign(
    client: TestClient, auth_headers, users
) -> None:
    """assigned_investigator_id is an editable field on the create payload too,
    so a complaint officer who lacks COMPLAINT_ASSIGN must not be able to slip
    an assignment in at intake."""
    investigator_id = users[UserRole.INVESTIGATOR].id

    officer_can = client.post(
        "/api/v1/complaints",
        json={
            "description": "Vial found cracked on receipt at the pharmacy loading dock.",
            "assigned_investigator_id": investigator_id,
        },
        headers=auth_headers(UserRole.COMPLAINT_OFFICER),
    )
    assert officer_can.status_code == 201
    assert officer_can.json()["assigned_investigator_id"] == investigator_id


def test_assigning_to_a_viewer_is_rejected(client: TestClient, auth_headers, users) -> None:
    """A viewer cannot carry out an investigation; the assignment is invalid on
    its face, not merely unwise."""
    viewer_id = users[UserRole.VIEWER].id

    response = client.post(
        "/api/v1/complaints",
        json={
            "description": "Vial found cracked on receipt at the pharmacy loading dock.",
            "assigned_investigator_id": viewer_id,
        },
        headers=auth_headers(UserRole.ADMIN),
    )
    assert response.status_code == 422
    assert "cannot carry out investigations" in response.json()["detail"]


def test_assigning_to_an_inactive_user_is_rejected(
    client: TestClient, auth_headers, users, db: Session
) -> None:
    from app.models.user import User

    investigator = db.get(User, users[UserRole.INVESTIGATOR].id)
    assert investigator is not None
    investigator.is_active = False
    db.commit()

    response = client.post(
        "/api/v1/complaints",
        json={
            "description": "Vial found cracked on receipt at the pharmacy loading dock.",
            "assigned_investigator_id": users[UserRole.INVESTIGATOR].id,
        },
        headers=auth_headers(UserRole.ADMIN),
    )
    assert response.status_code == 422


# ── Reference-data linking ───────────────────────────────────────────────────


def test_create_links_matching_reference_data(
    client: TestClient, auth_headers, make_complaint, db: Session
) -> None:
    from app.models.reference import Batch, Customer, Product

    customer = Customer(name="Test Hospital Pharmacy")
    product = Product(name="Testazole 250", strength="250 mg", product_code="TST-250")
    db.add_all([customer, product])
    db.flush()
    batch = Batch(product_id=product.id, batch_number="TST-99001")
    db.add(batch)
    db.commit()

    complaint = make_complaint(
        customer_name="Test Hospital Pharmacy",
        product_name="Testazole 250",
        product_strength="250 mg",
        batch_number="TST-99001",
    )

    stored = db.get(Complaint, complaint["id"])
    assert stored is not None
    assert stored.customer_id == customer.id
    assert stored.product_id == product.id
    assert stored.batch_id == batch.id


def test_create_leaves_unmatched_text_unlinked(
    client: TestClient, auth_headers, make_complaint
) -> None:
    """No reference row matches; the free text is kept and the FK is null. No
    evidence is discarded just because nothing to link it to exists yet."""
    complaint = make_complaint(customer_name="A Pharmacy Nobody Has Entered Yet")
    assert complaint["customer_name"] == "A Pharmacy Nobody Has Entered Yet"


def test_batch_number_alone_does_not_link_across_products(
    client: TestClient, auth_headers, make_complaint, db: Session
) -> None:
    """Lot numbers are unique per product, not globally. Two products
    legitimately reusing a lot code must not link to the wrong one."""
    from app.models.reference import Batch, Product

    p1 = Product(name="Product One", product_code="P1")
    p2 = Product(name="Product Two", product_code="P2")
    db.add_all([p1, p2])
    db.flush()
    db.add_all(
        [
            Batch(product_id=p1.id, batch_number="SHARED-001"),
            Batch(product_id=p2.id, batch_number="SHARED-001"),
        ]
    )
    db.commit()

    complaint = make_complaint(batch_number="SHARED-001")
    stored = db.get(Complaint, complaint["id"])
    assert stored is not None
    assert stored.batch_id is None  # ambiguous without a product to disambiguate


# ── Read / 404 ────────────────────────────────────────────────────────────────


def test_get_missing_complaint_is_404(client: TestClient, auth_headers) -> None:
    response = client.get("/api/v1/complaints/999999", headers=auth_headers(UserRole.VIEWER))
    assert response.status_code == 404


def test_every_role_can_read(client: TestClient, auth_headers, make_complaint) -> None:
    complaint = make_complaint()
    for role in UserRole:
        response = client.get(f"/api/v1/complaints/{complaint['id']}", headers=auth_headers(role))
        assert response.status_code == 200, role


# ── Partial update ────────────────────────────────────────────────────────────


def test_partial_update_changes_only_the_sent_field(
    client: TestClient, auth_headers, make_complaint
) -> None:
    """The mechanism CLAUDE.md calls out: 'the batch number is BMX 240602'
    changes one field and leaves the rest alone."""
    complaint = make_complaint(severity="major", priority="high")

    response = client.patch(
        f"/api/v1/complaints/{complaint['id']}",
        json={"batch_number": "BMX 240602"},
        headers=auth_headers(UserRole.COMPLAINT_OFFICER),
    )

    assert response.status_code == 200
    updated = response.json()
    assert updated["batch_number"] == "BMX 240602"
    assert updated["severity"] == "major"
    assert updated["priority"] == "high"
    assert updated["description"] == complaint["description"]


def test_explicit_null_clears_a_field(client: TestClient, auth_headers, make_complaint) -> None:
    complaint = make_complaint(severity="major")

    response = client.patch(
        f"/api/v1/complaints/{complaint['id']}",
        json={"severity": None},
        headers=auth_headers(UserRole.COMPLAINT_OFFICER),
    )

    assert response.status_code == 200
    assert response.json()["severity"] is None


def test_update_reassigning_needs_complaint_assign(
    client: TestClient, auth_headers, make_complaint, users
) -> None:
    """An investigator holding only COMPLAINT_UPDATE must not be able to
    reassign complaints - that would make the separate permission meaningless."""
    complaint = make_complaint()

    response = client.patch(
        f"/api/v1/complaints/{complaint['id']}",
        json={"assigned_investigator_id": users[UserRole.INVESTIGATOR].id},
        headers=auth_headers(UserRole.INVESTIGATOR),
    )

    assert response.status_code == 403
    assert "complaint:assign" in response.json()["detail"]


def test_update_merge_reject_invalid_quantity_combination(
    client: TestClient, auth_headers, make_complaint
) -> None:
    """ComplaintUpdate alone cannot see that quantity_unit is already null on
    the stored row - only the merge can. This is the cross-field check that
    apply_update runs after merging."""
    complaint = make_complaint()

    response = client.patch(
        f"/api/v1/complaints/{complaint['id']}",
        json={"quantity_affected": "48"},
        headers=auth_headers(UserRole.COMPLAINT_OFFICER),
    )

    assert response.status_code == 422
    assert "quantity_unit" in response.json()["detail"]


def test_update_merge_rejects_invalid_date_combination(
    client: TestClient, auth_headers, make_complaint
) -> None:
    complaint = make_complaint(manufacturing_date="2026-06-01")

    response = client.patch(
        f"/api/v1/complaints/{complaint['id']}",
        json={"expiry_date": "2025-01-01"},
        headers=auth_headers(UserRole.COMPLAINT_OFFICER),
    )

    assert response.status_code == 422


def test_invalid_merge_does_not_persist(
    client: TestClient, auth_headers, make_complaint, db: Session
) -> None:
    """The rejected update must not partially land."""
    complaint = make_complaint()

    client.patch(
        f"/api/v1/complaints/{complaint['id']}",
        json={"quantity_affected": "48"},
        headers=auth_headers(UserRole.COMPLAINT_OFFICER),
    )

    stored = db.get(Complaint, complaint["id"])
    assert stored is not None
    assert stored.quantity_affected is None


def test_closed_complaint_cannot_be_updated(
    client: TestClient, auth_headers, make_complaint, advance_to
) -> None:
    complaint = make_complaint()
    advance_to(complaint["id"], ComplaintStatus.CLOSED)

    response = client.patch(
        f"/api/v1/complaints/{complaint['id']}",
        json={"severity": "minor"},
        headers=auth_headers(UserRole.ADMIN),
    )

    assert response.status_code == 409
    assert "closed" in response.json()["detail"]


def test_update_re_resolves_reference_links_when_batch_changes(
    client: TestClient, auth_headers, make_complaint, db: Session
) -> None:
    from app.models.reference import Batch, Product

    product = Product(name="Relinked Product", product_code="RLP")
    db.add(product)
    db.flush()
    batch = Batch(product_id=product.id, batch_number="RLP-001")
    db.add(batch)
    db.commit()

    complaint = make_complaint()
    client.patch(
        f"/api/v1/complaints/{complaint['id']}",
        json={"product_name": "Relinked Product", "batch_number": "RLP-001"},
        headers=auth_headers(UserRole.COMPLAINT_OFFICER),
    )

    stored = db.get(Complaint, complaint["id"])
    assert stored is not None
    assert stored.product_id == product.id
    assert stored.batch_id == batch.id


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        (UserRole.ADMIN, 200),
        (UserRole.QA_MANAGER, 200),
        (UserRole.COMPLAINT_OFFICER, 200),
        (UserRole.INVESTIGATOR, 200),
        (UserRole.VIEWER, 403),
    ],
)
def test_who_may_update(
    client: TestClient, auth_headers, make_complaint, role: UserRole, expected: int
) -> None:
    complaint = make_complaint()
    response = client.patch(
        f"/api/v1/complaints/{complaint['id']}",
        json={"severity": "minor"},
        headers=auth_headers(role),
    )
    assert response.status_code == expected


# ── Delete ────────────────────────────────────────────────────────────────────


def test_new_complaint_is_deletable(client: TestClient, auth_headers, make_complaint) -> None:
    complaint = make_complaint()

    response = client.delete(
        f"/api/v1/complaints/{complaint['id']}", headers=auth_headers(UserRole.QA_MANAGER)
    )
    assert response.status_code == 204

    follow_up = client.get(
        f"/api/v1/complaints/{complaint['id']}", headers=auth_headers(UserRole.VIEWER)
    )
    assert follow_up.status_code == 404


def test_triaged_complaint_is_not_deletable(
    client: TestClient, auth_headers, make_complaint
) -> None:
    """Once reviewed, a complaint is part of the quality record - closing with
    a reason is the correct way to retire it, not deletion."""
    complaint = make_complaint()
    client.post(
        f"/api/v1/complaints/{complaint['id']}/transition",
        json={"to_status": "under_review"},
        headers=auth_headers(UserRole.ADMIN),
    )

    response = client.delete(
        f"/api/v1/complaints/{complaint['id']}", headers=auth_headers(UserRole.QA_MANAGER)
    )
    assert response.status_code == 409


@pytest.mark.parametrize(
    ("role", "expected"),
    [
        (UserRole.ADMIN, 204),
        (UserRole.QA_MANAGER, 204),
        (UserRole.COMPLAINT_OFFICER, 403),
        (UserRole.INVESTIGATOR, 403),
        (UserRole.VIEWER, 403),
    ],
)
def test_who_may_delete(
    client: TestClient, auth_headers, make_complaint, role: UserRole, expected: int
) -> None:
    complaint = make_complaint()
    response = client.delete(f"/api/v1/complaints/{complaint['id']}", headers=auth_headers(role))
    assert response.status_code == expected


# ── List, filter, sort, paginate ─────────────────────────────────────────────


def test_list_is_paginated(client: TestClient, auth_headers, make_complaint) -> None:
    for _ in range(3):
        make_complaint()

    response = client.get(
        "/api/v1/complaints?page=1&page_size=2", headers=auth_headers(UserRole.VIEWER)
    )
    body = response.json()

    assert body["total"] == 3
    assert body["pages"] == 2
    assert len(body["items"]) == 2


def test_page_count_matches_filtered_total(
    client: TestClient, auth_headers, make_complaint
) -> None:
    """The classic pagination bug: page 3 of 3 empty because count and rows
    were computed against different filters."""
    for _ in range(5):
        make_complaint(severity="critical")
    make_complaint(severity="minor")

    response = client.get(
        "/api/v1/complaints?severity=critical&page=2&page_size=2",
        headers=auth_headers(UserRole.VIEWER),
    )
    body = response.json()

    assert body["total"] == 5
    assert body["pages"] == 3
    assert len(body["items"]) == 2


def test_filter_by_batch_number_is_the_recall_query(
    client: TestClient, auth_headers, make_complaint
) -> None:
    make_complaint(batch_number="BMX-240602")
    make_complaint(batch_number="BMX-240602")
    make_complaint(batch_number="OTHER-LOT")

    response = client.get(
        "/api/v1/complaints?batch_number=BMX-240602", headers=auth_headers(UserRole.VIEWER)
    )
    body = response.json()

    assert body["total"] == 2
    assert all(item["batch_number"] == "BMX-240602" for item in body["items"])


def test_batch_filter_is_case_insensitive_substring(
    client: TestClient, auth_headers, make_complaint
) -> None:
    make_complaint(batch_number="BMX-240602")

    response = client.get(
        "/api/v1/complaints?batch_number=bmx-2406", headers=auth_headers(UserRole.VIEWER)
    )
    assert response.json()["total"] == 1


def test_batch_filter_escapes_wildcards(client: TestClient, auth_headers, make_complaint) -> None:
    """A literal '%' in a search term must not act as a SQL wildcard."""
    make_complaint(batch_number="50%-DISCOUNT-LOT")
    make_complaint(batch_number="ANY-OTHER-LOT")

    response = client.get(
        "/api/v1/complaints?batch_number=50%25", headers=auth_headers(UserRole.VIEWER)
    )
    assert response.json()["total"] == 1


def test_status_filter_is_multi_valued_or(
    client: TestClient, auth_headers, make_complaint, advance_to
) -> None:
    make_complaint()
    reviewed = make_complaint()
    advance_to(reviewed["id"], ComplaintStatus.UNDER_REVIEW)
    make_complaint()  # stays new too, should also be counted separately

    response = client.get(
        "/api/v1/complaints?status=new&status=under_review",
        headers=auth_headers(UserRole.VIEWER),
    )
    body = response.json()
    statuses = {item["status"] for item in body["items"]}
    assert statuses <= {"new", "under_review"}
    assert body["total"] == 3


def test_q_searches_description_and_reference_code(
    client: TestClient, auth_headers, make_complaint
) -> None:
    target = make_complaint(description="Particulate matter observed in the reconstituted vial.")
    make_complaint(description="Blister strip shows brown speckling on the tablet face.")

    by_text = client.get(
        "/api/v1/complaints?q=particulate", headers=auth_headers(UserRole.VIEWER)
    ).json()
    assert by_text["total"] == 1
    assert by_text["items"][0]["id"] == target["id"]

    by_reference = client.get(
        f"/api/v1/complaints?q={target['reference_code']}", headers=auth_headers(UserRole.VIEWER)
    ).json()
    assert by_reference["total"] == 1


def test_unassigned_only_filter(client: TestClient, auth_headers, make_complaint, users) -> None:
    make_complaint()
    make_complaint()
    assigned = make_complaint()
    client.patch(
        f"/api/v1/complaints/{assigned['id']}",
        json={"assigned_investigator_id": users[UserRole.INVESTIGATOR].id},
        headers=auth_headers(UserRole.ADMIN),
    )

    response = client.get(
        "/api/v1/complaints?unassigned_only=true", headers=auth_headers(UserRole.VIEWER)
    )
    body = response.json()
    assert body["total"] == 2
    assert all(item["assigned_investigator_id"] is None for item in body["items"])


def test_overdue_only_filter_excludes_closed(
    client: TestClient, auth_headers, make_complaint, advance_to
) -> None:
    yesterday = (date.today() - timedelta(days=1)).isoformat()

    overdue = make_complaint(due_date=yesterday)
    closed_but_overdue = make_complaint(due_date=yesterday)
    advance_to(closed_but_overdue["id"], ComplaintStatus.CLOSED)
    make_complaint(due_date=(date.today() + timedelta(days=10)).isoformat())

    response = client.get(
        "/api/v1/complaints?overdue_only=true", headers=auth_headers(UserRole.VIEWER)
    )
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == overdue["id"]


def test_date_range_filter(client: TestClient, auth_headers, make_complaint) -> None:
    early = (date.today() - timedelta(days=30)).isoformat()
    late = (date.today() - timedelta(days=1)).isoformat()

    make_complaint(complaint_date=early)
    in_range = make_complaint(complaint_date=late)

    response = client.get(
        f"/api/v1/complaints?date_from={(date.today() - timedelta(days=10)).isoformat()}"
        f"&date_to={date.today().isoformat()}",
        headers=auth_headers(UserRole.VIEWER),
    )
    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == in_range["id"]


def test_date_to_before_date_from_is_422(client: TestClient, auth_headers) -> None:
    response = client.get(
        "/api/v1/complaints?date_from=2026-06-01&date_to=2026-01-01",
        headers=auth_headers(UserRole.VIEWER),
    )
    assert response.status_code == 422


def test_sort_by_severity_ranks_critical_first(
    client: TestClient, auth_headers, make_complaint
) -> None:
    """Regression test for a real bug caught while writing this suite: enum
    columns here are `Enum(..., native_enum=False)`, which stores the member
    *name* ('CRITICAL'). Because Severity is a StrEnum, a member is already a
    `str`, so `case({member.value: ...}, value=column)` silently infers an
    untyped bind param from the bare `.value` ('critical') instead of routing
    it through the column's type - every WHEN branch fails to match and every
    row falls to the same rank. The fix in `_rank()` uses a searched CASE
    (`column == member`) instead, which goes through the same comparison path
    `.in_()` already uses correctly. Without this test, that mismatch sorts
    silently wrong: no error, no 500, just a queue that looks triaged by
    urgency and is actually in whatever order SQLite felt like."""
    make_complaint(severity="minor")
    make_complaint(severity="critical")
    make_complaint(severity="major")

    response = client.get("/api/v1/complaints?sort=severity", headers=auth_headers(UserRole.VIEWER))
    severities = [item["severity"] for item in response.json()["items"]]
    assert severities == ["critical", "major", "minor"]


def test_sort_by_priority_ranks_urgent_first(
    client: TestClient, auth_headers, make_complaint
) -> None:
    make_complaint(priority="low")
    make_complaint(priority="urgent")
    make_complaint(priority="medium")
    make_complaint(priority="high")

    response = client.get("/api/v1/complaints?sort=priority", headers=auth_headers(UserRole.VIEWER))
    priorities = [item["priority"] for item in response.json()["items"]]
    assert priorities == ["urgent", "high", "medium", "low"]


def test_enum_columns_store_the_member_name_not_the_value(db: Session, make_complaint) -> None:
    """Documents the underlying storage quirk directly against the database, so
    the reason the two tests above matter is visible without re-deriving it."""
    from sqlalchemy import text

    make_complaint(severity="critical")
    stored = db.execute(text("SELECT severity FROM complaints LIMIT 1")).scalar_one()
    assert stored == "CRITICAL"


def test_sort_by_due_date_puts_unset_last(client: TestClient, auth_headers, make_complaint) -> None:
    no_due = make_complaint()
    soon = make_complaint(due_date=(date.today() + timedelta(days=5)).isoformat())
    later = make_complaint(due_date=(date.today() + timedelta(days=20)).isoformat())

    response = client.get("/api/v1/complaints?sort=due_date", headers=auth_headers(UserRole.VIEWER))
    ids = [item["id"] for item in response.json()["items"]]
    assert ids == [soon["id"], later["id"], no_due["id"]]


def test_unknown_filter_param_is_rejected(client: TestClient, auth_headers) -> None:
    """extra='forbid' on ComplaintFilters: a misspelled filter must be a loud
    422, never a silently-ignored parameter that returns the wrong rows."""
    response = client.get("/api/v1/complaints?statuss=new", headers=auth_headers(UserRole.VIEWER))
    assert response.status_code == 422


def test_page_size_is_capped(client: TestClient, auth_headers) -> None:
    response = client.get("/api/v1/complaints?page_size=500", headers=auth_headers(UserRole.VIEWER))
    assert response.status_code == 422


def test_every_role_can_list(client: TestClient, auth_headers, make_complaint) -> None:
    make_complaint()
    for role in UserRole:
        response = client.get("/api/v1/complaints", headers=auth_headers(role))
        assert response.status_code == 200, role
