"""Complaint persistence: create, read, partial update, delete and search.

Three things in this module carry more weight than the rest:

1. **`apply_update` serialises with `exclude_unset=True`.** That single argument
   is what makes "the batch number is BMX 240602" change one column and leave
   the other thirty alone. `tests/test_complaints.py` guards it; CLAUDE.md
   forbids weakening it.

2. **`link_reference_data` resolves names to foreign keys.** The API exchanges
   human-readable text because AI extraction routinely yields a customer or
   batch that matches no existing row - so the text is always stored, and the
   FK is set only when a confident match exists. That is what makes "every
   complaint against batch BMX-240602" a reliable query rather than a guess
   about how someone typed a lot number.

3. **Reference codes are allocated, not computed.** See `next_reference_code`.
"""

from datetime import date
from typing import Any

from pydantic import ValidationError
from sqlalchemy import ColumnElement, Select, case, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.models.complaint import Complaint
from app.models.investigation import StatusTransition
from app.models.reference import Batch, Customer, Product
from app.models.user import User
from app.schemas.complaint import (
    ComplaintCreate,
    ComplaintFilters,
    ComplaintRead,
    ComplaintSort,
    ComplaintUpdate,
)
from app.schemas.enums import ComplaintStatus, Priority, Severity
from app.services.workflow import record_creation

REFERENCE_PREFIX = "CMP"

# Attempts to allocate a reference code before giving up. See the note in
# `create_complaint` - a retry is only ever needed when two requests allocate
# the same number concurrently, which the unique index catches.
_MAX_CODE_ATTEMPTS = 5

# Rank orders for sorting. The database stores these enums as strings, and
# alphabetical order is not severity order, so the ranking is made explicit
# rather than left to coincidence.
_SEVERITY_RANK: dict[Severity, int] = {
    Severity.CRITICAL: 0,
    Severity.MAJOR: 1,
    Severity.MINOR: 2,
}
_PRIORITY_RANK: dict[Priority, int] = {
    Priority.URGENT: 0,
    Priority.HIGH: 1,
    Priority.MEDIUM: 2,
    Priority.LOW: 3,
}


class ComplaintValidationError(Exception):
    """A partial update would leave the complaint violating its own contract.

    Raised by `apply_update`; the API maps it to 422. Distinct from Pydantic's
    ValidationError because by the time it is raised the payload itself was
    valid - it is the *merge* that is not.
    """


# ── Reference codes ───────────────────────────────────────────────────────────


def next_reference_code(db: Session, today: date | None = None) -> str:
    """The next unused complaint reference for the current year, e.g. CMP-2026-0042.

    Derived from the highest existing code rather than from a counter table or
    the primary key: the number appears in customer correspondence and
    regulatory filings, so it has to restart each year and read sensibly.

    Ordering is by length first, then lexically. Padding to four digits makes
    those two identical up to CMP-YYYY-9999, but a site logging its ten
    thousandth complaint in one year should get 10000, not a collision - and
    plain string ordering would place "9999" after "10000".
    """
    year = (today or date.today()).year
    prefix = f"{REFERENCE_PREFIX}-{year}-"

    highest = db.execute(
        select(Complaint.reference_code)
        .where(Complaint.reference_code.startswith(prefix))
        .order_by(func.length(Complaint.reference_code).desc(), Complaint.reference_code.desc())
        .limit(1)
    ).scalar_one_or_none()

    if highest is None:
        return f"{prefix}0001"

    try:
        sequence = int(highest.removeprefix(prefix)) + 1
    except ValueError:
        # A hand-edited or imported code that does not parse. Fall back to a
        # count rather than crashing intake; the unique index still protects us.
        sequence = (
            db.execute(
                select(func.count())
                .select_from(Complaint)
                .where(Complaint.reference_code.startswith(prefix))
            ).scalar_one()
            + 1
        )

    return f"{prefix}{sequence:04d}"


# ── Reference-data linking ────────────────────────────────────────────────────


def link_reference_data(db: Session, complaint: Complaint) -> None:
    """Point customer_id / product_id / batch_id at matching master records.

    Matching is exact and case-insensitive, never fuzzy. A wrong link is worse
    than no link: it would attribute a complaint to a batch that was never
    involved, and batch-level complaint counts are what recall decisions are
    made from. When nothing matches, the denormalised text stands alone and the
    FK stays null - no evidence is lost either way.
    """
    complaint.customer_id = _match_customer(db, complaint.customer_name)
    complaint.product_id = _match_product(db, complaint.product_name, complaint.product_strength)
    complaint.batch_id = _match_batch(db, complaint.batch_number, complaint.product_id)

    # A matched batch is authoritative about its own manufacture and expiry
    # dates; a complainant quoting a pack is not. Fill only what is missing so a
    # user's explicit entry is never overwritten.
    if complaint.batch_id is not None:
        batch = db.get(Batch, complaint.batch_id)
        if batch is not None:
            if complaint.manufacturing_date is None:
                complaint.manufacturing_date = batch.manufacturing_date
            if complaint.expiry_date is None:
                complaint.expiry_date = batch.expiry_date


def _match_customer(db: Session, name: str | None) -> int | None:
    if not name:
        return None
    return db.execute(
        select(Customer.id).where(func.lower(Customer.name) == name.strip().lower()).limit(1)
    ).scalar_one_or_none()


def _match_product(db: Session, name: str | None, strength: str | None) -> int | None:
    if not name:
        return None

    stmt = select(Product.id).where(func.lower(Product.name) == name.strip().lower())

    # Strength disambiguates same-named products (500 mg vs 250 mg). Only
    # narrow by it when it actually matches something, so a complaint quoting
    # an unfamiliar strength still links to the right product line.
    if strength:
        narrowed = db.execute(
            stmt.where(func.lower(Product.strength) == strength.strip().lower()).limit(1)
        ).scalar_one_or_none()
        if narrowed is not None:
            return narrowed

    return db.execute(stmt.limit(1)).scalar_one_or_none()


def _match_batch(db: Session, batch_number: str | None, product_id: int | None) -> int | None:
    if not batch_number:
        return None

    stmt = select(Batch.id).where(func.lower(Batch.batch_number) == batch_number.strip().lower())

    # Lot codes are unique per product, not globally, so an unqualified batch
    # number can legitimately match two rows. Without a product to disambiguate,
    # decline to link rather than pick one at random.
    if product_id is not None:
        return db.execute(stmt.where(Batch.product_id == product_id).limit(1)).scalar_one_or_none()

    matches = db.execute(stmt.limit(2)).scalars().all()
    return matches[0] if len(matches) == 1 else None


# ── Create / update / delete ──────────────────────────────────────────────────


def create_complaint(db: Session, payload: ComplaintCreate, actor: User | None) -> Complaint:
    """Persist a new complaint in status `new`, with its timeline started.

    The reference code is allocated inside a retry loop against a SAVEPOINT.
    Two concurrent intakes can read the same "highest" code; the unique index
    turns that into an IntegrityError, and the next attempt reads the number the
    winner just wrote. Without the savepoint the failed INSERT would poison the
    whole transaction and the caller would lose the complaint.
    """
    data = payload.model_dump()
    complaint = Complaint(**data, status=ComplaintStatus.NEW)
    complaint.created_by_id = actor.id if actor else None

    link_reference_data(db, complaint)

    last_error: IntegrityError | None = None
    for _ in range(_MAX_CODE_ATTEMPTS):
        complaint.reference_code = next_reference_code(db)
        savepoint = db.begin_nested()
        try:
            db.add(complaint)
            db.flush()
        except IntegrityError as exc:
            savepoint.rollback()
            last_error = exc
            continue
        break
    else:  # pragma: no cover - requires sustained concurrent collisions
        raise RuntimeError(
            f"Could not allocate a complaint reference code after {_MAX_CODE_ATTEMPTS} attempts"
        ) from last_error

    record_creation(db, complaint, actor)
    db.commit()
    db.refresh(complaint)
    return complaint


def apply_update(db: Session, complaint: Complaint, payload: ComplaintUpdate) -> Complaint:
    """Write only the fields the caller actually mentioned.

    `exclude_unset=True` is the whole point. A payload of `{"batch_number": ...}`
    produces exactly one assignment; a field omitted is untouched, while a field
    sent explicitly as null is cleared. Collapsing those two cases would make
    every partial AI edit a silent data-loss event.
    """
    changes = payload.model_dump(exclude_unset=True)
    for field, value in changes.items():
        setattr(complaint, field, value)

    # Re-resolve only when something that feeds a link actually changed;
    # otherwise an unrelated edit would re-run three queries for nothing.
    if changes.keys() & {"customer_name", "product_name", "product_strength", "batch_number"}:
        link_reference_data(db, complaint)

    _validate_merged(db, complaint)

    db.commit()
    db.refresh(complaint)
    return complaint


def _validate_merged(db: Session, complaint: Complaint) -> None:
    """Re-check the whole complaint against the contract after a partial edit.

    ComplaintUpdate can only see the fields in the payload, so its validation
    cannot catch a cross-field invariant that the *merge* breaks: sending just
    `quantity_affected` onto a complaint with no `quantity_unit` would store an
    ambiguous quantity, and sending just `expiry_date` could place expiry before
    manufacture. Both would then fail on the next read, turning a bad write into
    a 500 on an innocent GET.

    Validating the merged object here moves the failure back to the request that
    caused it, as a 422 the user can act on.
    """
    try:
        ComplaintRead.model_validate(complaint)
    except ValidationError as exc:
        # Restores the object to its persisted state; the edit never lands.
        db.rollback()
        raise ComplaintValidationError(
            "; ".join(e["msg"].removeprefix("Value error, ") for e in exc.errors())
        ) from exc


def delete_complaint(db: Session, complaint: Complaint) -> None:
    """Remove a complaint. The audit trail keeps a full snapshot of what went.

    Callers must check `is_deletable` first - this function does not, so that
    the policy lives in exactly one place and the API can return a 409 that
    explains itself.
    """
    db.delete(complaint)
    db.commit()


def is_deletable(complaint: Complaint) -> bool:
    """True only while a complaint is still untriaged.

    Deletion exists for the mis-entry caught seconds later - a duplicate, a test
    record, a complaint logged against the wrong tenant. Once a complaint has
    been reviewed it has become part of the quality record, and the correct way
    to retire it is to close it with a reason, leaving the trail intact.
    """
    return complaint.status is ComplaintStatus.NEW


# ── Listing ───────────────────────────────────────────────────────────────────


def _contains(column: InstrumentedAttribute[Any], value: str) -> ColumnElement[bool]:
    """Case-insensitive substring match with LIKE wildcards neutralised.

    Without the escape, a user searching for "50%" would match every row.
    """
    escaped = value.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return column.ilike(f"%{escaped}%", escape="\\")


def _apply_filters(stmt: Select[Any], filters: ComplaintFilters) -> Select[Any]:
    """AND together every filter the caller supplied. Values within one
    repeatable filter are OR'd - see ComplaintFilters."""
    if filters.q:
        term = filters.q
        stmt = stmt.where(
            or_(
                _contains(Complaint.reference_code, term),
                _contains(Complaint.description, term),
                _contains(Complaint.customer_name, term),
                _contains(Complaint.product_name, term),
                _contains(Complaint.batch_number, term),
            )
        )

    if filters.status:
        stmt = stmt.where(Complaint.status.in_(filters.status))
    if filters.severity:
        stmt = stmt.where(Complaint.severity.in_(filters.severity))
    if filters.priority:
        stmt = stmt.where(Complaint.priority.in_(filters.priority))
    if filters.complaint_type:
        stmt = stmt.where(Complaint.complaint_type.in_(filters.complaint_type))
    if filters.source:
        stmt = stmt.where(Complaint.source.in_(filters.source))

    if filters.customer_name:
        stmt = stmt.where(_contains(Complaint.customer_name, filters.customer_name))
    if filters.product_name:
        stmt = stmt.where(_contains(Complaint.product_name, filters.product_name))
    if filters.batch_number:
        stmt = stmt.where(_contains(Complaint.batch_number, filters.batch_number))

    if filters.assigned_investigator_id is not None:
        stmt = stmt.where(Complaint.assigned_investigator_id == filters.assigned_investigator_id)
    if filters.unassigned_only:
        stmt = stmt.where(Complaint.assigned_investigator_id.is_(None))

    if filters.overdue_only:
        # Mirrors Complaint.is_overdue, which cannot be used here because it is
        # a Python property. The two definitions are pinned together by a test.
        stmt = stmt.where(
            Complaint.due_date.is_not(None),
            Complaint.due_date < date.today(),
            Complaint.status != ComplaintStatus.CLOSED,
        )

    if filters.date_from is not None:
        stmt = stmt.where(Complaint.complaint_date >= filters.date_from)
    if filters.date_to is not None:
        stmt = stmt.where(Complaint.complaint_date <= filters.date_to)

    return stmt


def _rank(column: InstrumentedAttribute[Any], ranks: dict[Any, int]) -> ColumnElement[Any]:
    """Sort an enum column by meaning rather than by spelling. Unset values sort
    last, because a complaint nobody has triaged is not the most urgent one.

    Built as a searched CASE (`column == member`) rather than the `case(dict,
    value=column)` shorthand. The shorthand infers each WHEN literal's bind type
    from the Python value alone, with no visibility into `column`'s type - and
    since these enums are `StrEnum`, a member *is* a `str`, so the literal is
    bound untyped as its bare `.value` ('critical'). The column stores the
    member *name* ('CRITICAL'), because `Enum(..., native_enum=False)` encodes
    enums by name by default. Every WHEN would silently fail to match and every
    row would fall through to `else_`. A searched CASE instead compares through
    `column ==`, the same path `.in_()` already uses correctly elsewhere in this
    module, which runs the value through the column's own bind processor.
    """
    return case(*((column == member, rank) for member, rank in ranks.items()), else_=len(ranks))


def _apply_sort(stmt: Select[Any], sort: ComplaintSort) -> Select[Any]:
    """Order the page. Every ordering ends with a tiebreak on id so that
    pagination is stable - without it, rows created in the same second can swap
    between pages and a reviewer sees one twice and another never."""
    if sort is ComplaintSort.OLDEST:
        return stmt.order_by(Complaint.created_at.asc(), Complaint.id.asc())
    if sort is ComplaintSort.SEVERITY:
        return stmt.order_by(
            _rank(Complaint.severity, _SEVERITY_RANK).asc(),
            Complaint.created_at.desc(),
            Complaint.id.desc(),
        )
    if sort is ComplaintSort.PRIORITY:
        return stmt.order_by(
            _rank(Complaint.priority, _PRIORITY_RANK).asc(),
            Complaint.created_at.desc(),
            Complaint.id.desc(),
        )
    if sort is ComplaintSort.DUE_DATE:
        # Explicit nulls-last rather than NULLS LAST: SQLite's support arrived
        # late enough that a CASE is the portable choice, and this runs on both.
        return stmt.order_by(
            case((Complaint.due_date.is_(None), 1), else_=0).asc(),
            Complaint.due_date.asc(),
            Complaint.id.asc(),
        )
    if sort is ComplaintSort.REFERENCE:
        return stmt.order_by(Complaint.reference_code.asc(), Complaint.id.asc())

    return stmt.order_by(Complaint.created_at.desc(), Complaint.id.desc())


def list_complaints(db: Session, filters: ComplaintFilters) -> tuple[list[Complaint], int]:
    """One page of complaints and the total number matching, before paging.

    The count is issued against the same filtered statement so the pager can
    never disagree with the rows - the classic bug where page 3 of 3 is empty.
    """
    base = _apply_filters(select(Complaint), filters)

    total = db.execute(
        select(func.count()).select_from(base.with_only_columns(Complaint.id).subquery())
    ).scalar_one()

    page = _apply_sort(base, filters.sort)
    page = page.offset((filters.page - 1) * filters.page_size).limit(filters.page_size)

    return list(db.execute(page).scalars()), total


def timeline(db: Session, complaint_id: int) -> list[StatusTransition]:
    """The complaint's status history, oldest first.

    Ordered by id rather than created_at: several transitions can share a
    timestamp, and the insertion order is the true sequence.
    """
    return list(
        db.execute(
            select(StatusTransition)
            .where(StatusTransition.complaint_id == complaint_id)
            .order_by(StatusTransition.id.asc())
        ).scalars()
    )
