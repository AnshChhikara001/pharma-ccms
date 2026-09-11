"""The demo dataset, and the loader that turns it into rows.

Two different things are checked here. `COMPLAINT_SEEDS` is content - hand
authored, reviewed by eye - so these tests do not re-review its prose; they
check the structural invariants a future edit could break without anyone
noticing: a batch number that stops matching any `BatchSpec`, a severity that
drifts from its priority, a due date computed wrong. Then `seed_complaints`
itself is checked end-to-end through `python -m seeds.run`'s actual path,
because seed data that only *looks* right in the dataclass is worth nothing if
the loader mangles it on the way into the database.
"""

from datetime import date

from sqlalchemy.orm import Session

from app.models.complaint import Complaint
from app.schemas.enums import ComplaintStatus, Priority, Severity
from seeds.complaint_data import COMPLAINT_SEEDS
from seeds.complaints import seed_complaints
from seeds.reference import seed_reference_data
from seeds.users import seed_users

# Priorities a given severity may reasonably carry. Not a strict function - a
# major defect can be urgent or high depending on context - but a critical
# complaint sitting at "low" priority would be a real authoring mistake this
# guards against.
_PLAUSIBLE_PRIORITY: dict[Severity, set[Priority]] = {
    Severity.CRITICAL: {Priority.URGENT, Priority.HIGH},
    Severity.MAJOR: {Priority.URGENT, Priority.HIGH, Priority.MEDIUM},
    Severity.MINOR: {Priority.HIGH, Priority.MEDIUM, Priority.LOW},
}


# ── The corpus, as data ───────────────────────────────────────────────────────


def test_corpus_has_the_documented_shape() -> None:
    assert 24 <= len(COMPLAINT_SEEDS) <= 30


def test_corpus_spans_every_lifecycle_status() -> None:
    statuses = {seed.target_status for seed in COMPLAINT_SEEDS}
    assert statuses == set(ComplaintStatus)


def test_corpus_is_weighted_toward_the_early_queue() -> None:
    """A demo queue that is mostly closed complaints does not look like a
    working queue."""
    early = {ComplaintStatus.NEW, ComplaintStatus.UNDER_REVIEW, ComplaintStatus.INVESTIGATION}
    early_count = sum(1 for seed in COMPLAINT_SEEDS if seed.target_status in early)
    assert early_count > len(COMPLAINT_SEEDS) / 2


def test_severity_and_priority_stay_coherent() -> None:
    offenders = [
        (seed.customer_name, seed.severity, seed.priority)
        for seed in COMPLAINT_SEEDS
        if seed.priority not in _PLAUSIBLE_PRIORITY[seed.severity]
    ]
    assert not offenders, f"Severity/priority mismatches: {offenders}"


def test_a_shared_batch_carries_several_complaints() -> None:
    """The recall query and the duplicate-detection demo both need a lot that
    several different complaints actually point at."""
    counts: dict[str, int] = {}
    for seed in COMPLAINT_SEEDS:
        counts[seed.batch_number] = counts.get(seed.batch_number, 0) + 1

    shared = [batch for batch, count in counts.items() if count >= 3]
    assert shared, "No batch number is shared by three or more seeded complaints"


def test_some_complaints_are_overdue_and_still_open() -> None:
    overdue = [
        seed
        for seed in COMPLAINT_SEEDS
        if seed.due_in_days is not None
        and seed.days_ago > seed.due_in_days
        and seed.target_status is not ComplaintStatus.CLOSED
    ]
    assert overdue, "No seeded complaint is both overdue and still open"


def test_days_ago_spans_roughly_the_last_six_months() -> None:
    assert max(seed.days_ago for seed in COMPLAINT_SEEDS) >= 120


def test_descriptions_never_assert_a_root_cause() -> None:
    """A complaint records what was observed. Determining why is the
    investigation's job - a seeded description that already names a cause would
    misrepresent what this screen is for."""
    root_cause_language = ("root cause", "caused by", "due to a defect in", "was contaminated by")
    offenders = [
        seed.customer_name
        for seed in COMPLAINT_SEEDS
        if any(phrase in seed.description.lower() for phrase in root_cause_language)
    ]
    assert not offenders, f"Descriptions asserting a cause: {offenders}"


def test_quantity_fields_are_never_half_populated() -> None:
    """Mirrors the contract rule in ComplaintBase: a quantity needs a unit."""
    offenders = [
        seed.customer_name
        for seed in COMPLAINT_SEEDS
        if (seed.quantity_affected is None) != (seed.quantity_unit is None)
    ]
    assert not offenders, f"Half-populated quantity fields: {offenders}"


# ── The corpus, loaded ────────────────────────────────────────────────────────


def test_seed_loader_creates_every_complaint(db: Session) -> None:
    users = {user.role: user for user in seed_users(db)}
    seed_reference_data(db)

    complaints = seed_complaints(db, users)

    assert len(complaints) == len(COMPLAINT_SEEDS)
    assert db.query(Complaint).count() == len(COMPLAINT_SEEDS)


def test_seed_loader_is_idempotent(db: Session) -> None:
    """Running the seed twice must not double the data - `python -m seeds.run`
    is documented as safe to repeat."""
    users = {user.role: user for user in seed_users(db)}
    seed_reference_data(db)

    seed_complaints(db, users)
    seed_complaints(db, users)

    assert db.query(Complaint).count() == len(COMPLAINT_SEEDS)


def test_seeded_complaints_have_valid_reference_codes(db: Session) -> None:
    users = {user.role: user for user in seed_users(db)}
    seed_reference_data(db)
    complaints = seed_complaints(db, users)

    codes = [c.reference_code for c in complaints]
    assert len(codes) == len(set(codes)), "Duplicate reference codes"
    assert all(code.startswith(f"CMP-{date.today().year}-") for code in codes)


def test_seeded_complaints_reach_their_declared_target_status(db: Session) -> None:
    users = {user.role: user for user in seed_users(db)}
    seed_reference_data(db)
    complaints = seed_complaints(db, users)

    by_description = {c.description: c for c in complaints}
    for seed in COMPLAINT_SEEDS:
        assert by_description[seed.description].status == seed.target_status


def test_seeded_complaints_reaching_investigation_have_an_investigator(db: Session) -> None:
    """The workflow engine will not admit a complaint into `investigation`
    without one - seeded data proves the loader actually satisfies its own
    precondition rather than working around it."""
    users = {user.role: user for user in seed_users(db)}
    seed_reference_data(db)
    complaints = seed_complaints(db, users)

    from app.services.workflow import LIFECYCLE

    investigation_index = LIFECYCLE.index(ComplaintStatus.INVESTIGATION)
    for complaint in complaints:
        if LIFECYCLE.index(complaint.status) >= investigation_index:
            assert complaint.assigned_investigator_id is not None, complaint.reference_code


def test_seeded_batch_numbers_all_resolve_to_a_real_batch(db: Session) -> None:
    """Cross-file linkage: every batch_number in the corpus must match a batch
    seeded by `seed_reference_data`, or the loader's reference-data linking
    would leave it unlinked and the recall query would miss it."""
    users = {user.role: user for user in seed_users(db)}
    seed_reference_data(db)
    complaints = seed_complaints(db, users)

    unlinked = [c.reference_code for c in complaints if c.batch_number and c.batch_id is None]
    assert not unlinked, f"Seeded complaints whose batch never linked: {unlinked}"


def test_seeded_overdue_complaints_are_flagged_overdue(db: Session) -> None:
    users = {user.role: user for user in seed_users(db)}
    seed_reference_data(db)
    complaints = seed_complaints(db, users)

    expected_overdue = {
        seed.customer_name
        for seed in COMPLAINT_SEEDS
        if seed.due_in_days is not None
        and seed.days_ago > seed.due_in_days
        and seed.target_status is not ComplaintStatus.CLOSED
    }
    actual_overdue = {c.customer_name for c in complaints if c.is_overdue}
    assert actual_overdue == expected_overdue


def test_seeded_complaint_timelines_start_at_new(db: Session) -> None:
    """Every complaint the loader creates goes through create_complaint, so
    every one must have an opening timeline row - proof the loader used the
    real service rather than inserting rows directly."""
    users = {user.role: user for user in seed_users(db)}
    seed_reference_data(db)
    complaints = seed_complaints(db, users)

    for complaint in complaints:
        opening = [t for t in complaint.transitions if t.from_status is None]
        assert len(opening) == 1, complaint.reference_code
        assert opening[0].to_status == ComplaintStatus.NEW
