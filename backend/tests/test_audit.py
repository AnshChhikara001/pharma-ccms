"""The automatic audit trail.

The property under test is not "audit entries can be written" - it is that they
are written **without anyone asking**. Every test here mutates data through
ordinary model operations, never touching AuditEntry, and then asserts the trail
appeared anyway. That is what makes the trail trustworthy: a future endpoint
cannot forget to call something it never calls.
"""

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AuditEntry, Complaint, Customer, Product, User
from app.schemas.enums import AuditAction, ComplaintStatus, Severity, UserRole


def _entries(db: Session, entity_type: str | None = None) -> list[AuditEntry]:
    stmt = select(AuditEntry).order_by(AuditEntry.id)
    if entity_type:
        stmt = stmt.where(AuditEntry.entity_type == entity_type)
    return list(db.execute(stmt).scalars())


def _make_complaint(db: Session, **overrides: object) -> Complaint:
    defaults: dict[str, object] = {
        "reference_code": "CMP-2026-0001",
        "description": "Brown speckling observed on tablet surface.",
        "status": ComplaintStatus.NEW,
    }
    defaults.update(overrides)
    complaint = Complaint(**defaults)  # type: ignore[arg-type]
    db.add(complaint)
    db.commit()
    return complaint


# ── Creation ─────────────────────────────────────────────────────────────────


def test_creating_a_complaint_writes_an_audit_entry(db: Session) -> None:
    _make_complaint(db)

    entries = _entries(db, "Complaint")
    assert len(entries) == 1
    assert entries[0].action is AuditAction.CREATED
    assert entries[0].summary == "Complaint CMP-2026-0001 created"


def test_created_entry_records_the_new_row_id(db: Session) -> None:
    """The id does not exist until flush, so it has to be backfilled afterwards.
    Getting this wrong leaves every insert pointing at entity_id 0."""
    complaint = _make_complaint(db)

    entry = _entries(db, "Complaint")[0]
    assert entry.entity_id == complaint.id
    assert entry.entity_id != 0


# ── Updates ──────────────────────────────────────────────────────────────────


def test_update_records_a_before_and_after_diff(db: Session) -> None:
    complaint = _make_complaint(db, severity=Severity.MINOR)

    complaint.severity = Severity.CRITICAL
    db.commit()

    update = _entries(db, "Complaint")[-1]
    assert update.action is AuditAction.UPDATED
    assert update.changes is not None
    # StrEnum serialises to its wire value, so the trail reads the same way the
    # API does - "minor", not "Severity.MINOR".
    assert update.changes["severity"] == {"old": "minor", "new": "critical"}


def test_status_change_is_recorded_as_its_own_action(db: Session) -> None:
    """A reviewer scans the trail for lifecycle movement, so it must be
    distinguishable from an ordinary field edit."""
    complaint = _make_complaint(db)

    complaint.status = ComplaintStatus.UNDER_REVIEW
    db.commit()

    entry = _entries(db, "Complaint")[-1]
    assert entry.action is AuditAction.STATUS_CHANGED
    assert "under_review" in (entry.summary or "").lower()


def test_unchanged_save_writes_no_entry(db: Session) -> None:
    """Committing without a real change must not pollute the trail."""
    complaint = _make_complaint(db)
    before = len(_entries(db))

    complaint.description = complaint.description  # no-op
    db.commit()

    assert len(_entries(db)) == before


def test_timestamp_churn_is_not_audited(db: Session) -> None:
    """updated_at moves on every write; recording it would bury real changes."""
    complaint = _make_complaint(db)
    complaint.priority = None
    complaint.severity = Severity.MAJOR
    db.commit()

    entry = _entries(db, "Complaint")[-1]
    assert entry.changes is not None
    assert "updated_at" not in entry.changes
    assert "created_at" not in entry.changes


# ── Deletion ─────────────────────────────────────────────────────────────────


def test_deletion_is_recorded_and_survives_the_row(db: Session) -> None:
    """The trail is intentionally not a foreign key. An auditor asking what
    happened to a deleted complaint must still get an answer."""
    complaint = _make_complaint(db)
    complaint_id = complaint.id

    db.delete(complaint)
    db.commit()

    assert db.get(Complaint, complaint_id) is None

    deletion = _entries(db, "Complaint")[-1]
    assert deletion.action is AuditAction.DELETED
    assert deletion.entity_id == complaint_id


# ── Redaction ────────────────────────────────────────────────────────────────


def test_password_hash_is_never_written_to_the_trail(db: Session) -> None:
    user = User(
        email="audit.subject@pharmaco.com",
        full_name="Audit Subject",
        hashed_password="$2b$12$averysecretlookinghashvalue",
        role=UserRole.VIEWER,
    )
    db.add(user)
    db.commit()

    user.hashed_password = "$2b$12$adifferentsecrethashvalue"
    db.commit()

    for entry in _entries(db, "User"):
        serialised = str(entry.changes)
        assert "averysecretlooking" not in serialised
        assert "adifferentsecret" not in serialised
        if entry.changes and "hashed_password" in entry.changes:
            assert entry.changes["hashed_password"]["new"] == "[redacted]"


# ── Scope ────────────────────────────────────────────────────────────────────


def test_reference_data_is_not_audited(db: Session) -> None:
    """Products and customers are master data maintained outside the complaint
    workflow. Auditing them would drown the signal."""
    db.add(Customer(name="Apollo Pharmacy"))
    db.add(Product(name="Amoxicillin", strength="500 mg"))
    db.commit()

    assert _entries(db, "Customer") == []
    assert _entries(db, "Product") == []


def test_audit_entries_do_not_audit_themselves(db: Session) -> None:
    """If AuditEntry were audited, every write would recurse."""
    _make_complaint(db)
    assert _entries(db, "AuditEntry") == []


# ── Actor attribution ────────────────────────────────────────────────────────


def test_changes_made_through_the_api_record_the_acting_user(
    client, auth_headers, db: Session
) -> None:
    """End-to-end: the actor reaches the listener via the request ContextVar,
    with no endpoint code passing it along."""
    response = client.post(
        "/api/v1/auth/users",
        json={
            "email": "traceable@pharmaco.com",
            "full_name": "Traceable Person",
            "password": "Str0ng-Pass!",
            "role": "viewer",
        },
        headers=auth_headers(UserRole.ADMIN),
    )
    assert response.status_code == 201

    created = (
        db.execute(
            select(AuditEntry)
            .where(AuditEntry.entity_type == "User", AuditEntry.action == AuditAction.CREATED)
            .order_by(AuditEntry.id.desc())
        )
        .scalars()
        .first()
    )

    assert created is not None
    assert created.actor_id is not None, "audit entry should name who acted"


def test_multiple_changes_accumulate_in_order(db: Session) -> None:
    complaint = _make_complaint(db)

    complaint.status = ComplaintStatus.UNDER_REVIEW
    db.commit()
    complaint.status = ComplaintStatus.INVESTIGATION
    db.commit()
    complaint.due_date = date(2026, 12, 31)
    db.commit()

    entries = _entries(db, "Complaint")
    assert [e.action for e in entries] == [
        AuditAction.CREATED,
        AuditAction.STATUS_CHANGED,
        AuditAction.STATUS_CHANGED,
        AuditAction.UPDATED,
    ]


def test_trail_is_append_only_in_practice(db: Session) -> None:
    """Nothing in the application ever updates or deletes an entry; this pins
    that expectation so a future change has to argue with a test."""
    _make_complaint(db)
    count = db.execute(select(func.count()).select_from(AuditEntry)).scalar()

    complaint = db.execute(select(Complaint)).scalar_one()
    complaint.severity = Severity.MAJOR
    db.commit()

    new_count = db.execute(select(func.count()).select_from(AuditEntry)).scalar()
    assert new_count is not None and count is not None
    assert new_count > count, "entries are added, never replaced"


def test_summary_uses_the_real_id_for_entities_without_a_reference_code(
    db: Session,
) -> None:
    """The summary is composed at before_flush, when an inserted row has no id
    yet. Without recomputing it after the flush, a User entry reads
    "User #None created" in the timeline."""
    user = User(
        email="labelled@pharmaco.com",
        full_name="Labelled Person",
        hashed_password="$2b$12$placeholder",
        role=UserRole.VIEWER,
    )
    db.add(user)
    db.commit()

    entry = _entries(db, "User")[0]
    assert "None" not in (entry.summary or "")
    assert entry.summary == f"User #{user.id} created"
