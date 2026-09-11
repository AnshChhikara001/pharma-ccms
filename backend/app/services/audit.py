"""Automatic audit trail via SQLAlchemy session events.

The design goal is that **no endpoint ever writes an audit entry**. Entries are
derived from the session's own change set just before flush, so any code path
that mutates an audited model is recorded - including ones written later by
someone who has never read this file.

How the actor is known
----------------------
Audit entries need "who", but a session event has no access to the request. The
actor is therefore carried in a ContextVar set by middleware for the duration of
the request. Async-safe and request-scoped; a background job simply records no
actor rather than mis-attributing one.

Why before_flush
----------------
`before_flush` still has access to the original values of changed columns, so a
real before/after diff can be captured. After flush, the old values are gone.
"""

from contextvars import ContextVar
from typing import Any, cast

from sqlalchemy import Table, event, inspect
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import get_history

from app.models.audit import AuditEntry
from app.models.complaint import AIAssessmentRecord, Complaint, ComplaintDocument
from app.models.investigation import CAPA, Investigation, RootCause, StatusTransition
from app.models.user import User
from app.schemas.enums import AuditAction

# Set by AuditContextMiddleware for the life of a request.
_current_actor: ContextVar[tuple[int, str] | None] = ContextVar("current_actor", default=None)

# Models whose changes are recorded. Reference data (products, customers,
# batches) is deliberately excluded: it is master data maintained outside the
# complaint workflow, and auditing it would bury the signal.
AUDITED_MODELS: tuple[type, ...] = (
    Complaint,
    ComplaintDocument,
    AIAssessmentRecord,
    Investigation,
    RootCause,
    CAPA,
    StatusTransition,
    User,
)

# Never recorded in a diff, at any cost.
_REDACTED_FIELDS = frozenset({"hashed_password"})

# Churn with no audit value; recording them would drown real changes.
_IGNORED_FIELDS = frozenset({"updated_at", "created_at"})


def set_audit_actor(user_id: int | None, email: str | None) -> object:
    """Bind the acting user for this request. Returns a reset token."""
    return _current_actor.set((user_id, email) if user_id is not None else None)  # type: ignore[arg-type]


def reset_audit_actor(token: object) -> None:
    """Restore the previous actor binding."""
    _current_actor.reset(token)  # type: ignore[arg-type]


def _serialise(value: Any) -> Any:
    """Coerce a column value into something JSON can hold."""
    if value is None or isinstance(value, str | int | float | bool):
        return value
    return str(value)


def _diff(obj: object) -> dict[str, dict[str, Any]]:
    """Field-level before/after for a dirty instance."""
    changes: dict[str, dict[str, Any]] = {}
    state = inspect(obj)
    if state is None:  # not a mapped instance; nothing to diff
        return changes

    for attr in state.mapper.column_attrs:
        key = attr.key
        if key in _IGNORED_FIELDS:
            continue

        history = get_history(obj, key)
        if not history.has_changes():
            continue

        if key in _REDACTED_FIELDS:
            changes[key] = {"old": "[redacted]", "new": "[redacted]"}
            continue

        old = history.deleted[0] if history.deleted else None
        new = history.added[0] if history.added else None
        changes[key] = {"old": _serialise(old), "new": _serialise(new)}

    return changes


def _snapshot(obj: object) -> dict[str, Any]:
    """Full column snapshot, used for inserts."""
    state = inspect(obj)
    if state is None:
        return {}
    return {
        attr.key: _serialise(getattr(obj, attr.key))
        for attr in state.mapper.column_attrs
        if attr.key not in _IGNORED_FIELDS and attr.key not in _REDACTED_FIELDS
    }


def _entry(obj: object, action: AuditAction, changes: dict[str, Any] | None) -> AuditEntry:
    actor = _current_actor.get()
    actor_id, actor_email = actor if actor else (None, None)

    entity_id = getattr(obj, "id", None)
    return AuditEntry(
        entity_type=type(obj).__name__,
        # 0 for a pending insert; corrected in after_flush once the PK exists.
        entity_id=entity_id if entity_id is not None else 0,
        action=action,
        changes=changes or None,
        actor_id=actor_id,
        actor_email=actor_email,
        summary=_summarise(obj, action, changes),
    )


def _summarise(obj: object, action: AuditAction, changes: dict[str, Any] | None) -> str:
    """Short human-readable line for the timeline UI."""
    label = getattr(obj, "reference_code", None) or f"#{getattr(obj, 'id', '?')}"
    name = type(obj).__name__
    if action is AuditAction.CREATED:
        return f"{name} {label} created"
    if action is AuditAction.STATUS_CHANGED:
        new = (changes or {}).get("status", {}).get("new")
        return f"{name} {label} moved to {new}"
    if changes:
        fields = ", ".join(sorted(changes)[:5])
        return f"{name} {label} updated: {fields}"
    return f"{name} {label} {action.value}"


def _register(session: Session) -> None:
    """Collect audit entries from the session's pending change set."""
    pending: list[tuple[AuditEntry, object]] = []

    for obj in session.new:
        if isinstance(obj, AUDITED_MODELS):
            pending.append((_entry(obj, AuditAction.CREATED, _snapshot(obj)), obj))

    for obj in session.dirty:
        if not isinstance(obj, AUDITED_MODELS) or not session.is_modified(obj):
            continue
        changes = _diff(obj)
        if not changes:
            continue
        # A status change is called out specifically - it is the event a
        # reviewer scans the trail for.
        action = AuditAction.STATUS_CHANGED if "status" in changes else AuditAction.UPDATED
        pending.append((_entry(obj, action, changes), obj))

    for obj in session.deleted:
        if isinstance(obj, AUDITED_MODELS):
            pending.append((_entry(obj, AuditAction.DELETED, _snapshot(obj)), obj))

    for entry, _ in pending:
        session.add(entry)

    if pending:
        # Stash so after_flush can backfill primary keys for inserted rows.
        session.info.setdefault("_pending_audit", []).extend(pending)


def _backfill_ids(session: Session) -> None:
    """Fill in entity_id for rows that had no primary key at before_flush time.

    An inserted object only receives its id during the flush, so its audit entry
    is written with a placeholder of 0. Correcting the Python attribute here is
    not enough - the audit row has *already* been INSERTed in this same flush,
    and a plain attribute assignment after the fact produces no second UPDATE.
    So the correction is issued as explicit SQL.

    The statement is built against the Core table rather than the ORM class on
    purpose: passing a list of parameter dicts to an ORM-enabled update puts
    SQLAlchemy into "bulk update by primary key" mode, which demands an `id` key
    in every dict and rejects a custom WHERE clause. A Core update has no such
    semantics. There are only ever a handful of corrections per flush, so
    issuing them one at a time costs nothing.

    autoflush is suppressed because emitting SQL inside after_flush would
    otherwise re-enter the flush machinery.
    """
    pending = session.info.pop("_pending_audit", [])
    if not pending:
        return

    # cast: __table__ is typed as the broader FromClause, but an ORM model's
    # table is always a Table, which is what exposes .update() and .c.
    table = cast(Table, AuditEntry.__table__)
    with session.no_autoflush:
        for entry, obj in pending:
            if entry.entity_id != 0:
                continue
            actual = getattr(obj, "id", None)
            if actual is None:
                continue
            entry.entity_id = actual

            # The summary was composed before the id existed, so an entity with
            # no reference_code rendered as "User #None created". Recompute it
            # now that the real id is known.
            summary = _summarise(obj, entry.action, entry.changes)
            entry.summary = summary

            if entry.id is not None:
                session.execute(
                    table.update()
                    .where(table.c.id == entry.id)
                    .values(entity_id=actual, summary=summary)
                )


def install_audit_listeners() -> None:
    """Attach the listeners. Idempotent, so repeated calls are harmless."""
    if not event.contains(Session, "before_flush", _before_flush):
        event.listen(Session, "before_flush", _before_flush)
    if not event.contains(Session, "after_flush", _after_flush):
        event.listen(Session, "after_flush", _after_flush)


def _before_flush(session: Session, _flush_context: object, _instances: object) -> None:
    _register(session)


def _after_flush(session: Session, _flush_context: object) -> None:
    _backfill_ids(session)
