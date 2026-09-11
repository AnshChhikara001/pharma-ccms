"""The complaint lifecycle, defined once as a table.

`enums.py` promises that legal transitions live here, and this is that promise
kept. The entire workflow policy is the two structures below - the legal moves
and the permissions each target demands. Everything else in this module reads
them; no endpoint, service or AI tool encodes a lifecycle rule of its own.

Why a table rather than code
----------------------------
A reviewer - or an auditor - can read the whole policy in one screen and check
it against the SOP. The test suite asserts the table verbatim, so a later edit
that quietly permits "new -> closed" fails the build instead of shipping. And
because the same table is served to the frontend at `GET /meta/workflow`, the
buttons a user sees are derived from the rule the server enforces rather than
from a second, hand-maintained list that can drift.

The shape of the lifecycle
--------------------------
    new -> under_review -> investigation -> root_cause_identified
        -> capa_required -> qa_review -> closed

Forward is the happy path. Two shortcuts and three returns are also legal, and
each exists for a reason a QA function would recognise:

  * under_review -> qa_review           a complaint judged not to be a quality
                                        defect still needs a QA decision, but
                                        not a formal investigation.
  * root_cause_identified -> qa_review  not every confirmed root cause warrants
                                        a CAPA; that judgement is QA's.
  * anything -> investigation/under_review
                                        work sent back for more evidence. These
                                        are the "returns", and they require a
                                        reason - an unexplained regression in a
                                        complaint's lifecycle is exactly what an
                                        audit finding is made of.

`closed` is terminal. Reopening a closed complaint would rewrite a record that
has already been signed off; the regulated answer is to raise a new complaint
that references it, not to reanimate the old one.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.rbac import Permission
from app.models.complaint import Complaint
from app.models.investigation import StatusTransition
from app.models.user import User
from app.schemas.enums import ComplaintStatus

# Ordered lifecycle. Position in this tuple is what makes a transition
# "forward" or "backward"; nothing else depends on the order.
LIFECYCLE: tuple[ComplaintStatus, ...] = (
    ComplaintStatus.NEW,
    ComplaintStatus.UNDER_REVIEW,
    ComplaintStatus.INVESTIGATION,
    ComplaintStatus.ROOT_CAUSE_IDENTIFIED,
    ComplaintStatus.CAPA_REQUIRED,
    ComplaintStatus.QA_REVIEW,
    ComplaintStatus.CLOSED,
)

_ORDER: dict[ComplaintStatus, int] = {status: i for i, status in enumerate(LIFECYCLE)}

# THE table. Every legal move in the system.
LEGAL_TRANSITIONS: dict[ComplaintStatus, frozenset[ComplaintStatus]] = {
    ComplaintStatus.NEW: frozenset({ComplaintStatus.UNDER_REVIEW}),
    ComplaintStatus.UNDER_REVIEW: frozenset(
        {ComplaintStatus.INVESTIGATION, ComplaintStatus.QA_REVIEW}
    ),
    ComplaintStatus.INVESTIGATION: frozenset(
        {ComplaintStatus.ROOT_CAUSE_IDENTIFIED, ComplaintStatus.UNDER_REVIEW}
    ),
    ComplaintStatus.ROOT_CAUSE_IDENTIFIED: frozenset(
        {
            ComplaintStatus.CAPA_REQUIRED,
            ComplaintStatus.QA_REVIEW,
            ComplaintStatus.INVESTIGATION,
        }
    ),
    ComplaintStatus.CAPA_REQUIRED: frozenset(
        {ComplaintStatus.QA_REVIEW, ComplaintStatus.INVESTIGATION}
    ),
    ComplaintStatus.QA_REVIEW: frozenset({ComplaintStatus.CLOSED, ComplaintStatus.INVESTIGATION}),
    ComplaintStatus.CLOSED: frozenset(),
}

# Extra permission a *target* status demands, on top of WORKFLOW_TRANSITION.
# Closure is the one irreversible act in the lifecycle, so it is the one the
# role matrix restricts - to QA managers and admins. See core/rbac.py.
_EXTRA_PERMISSION: dict[ComplaintStatus, Permission] = {
    ComplaintStatus.CLOSED: Permission.WORKFLOW_CLOSE,
}


class WorkflowError(Exception):
    """Base for lifecycle rule violations. The API maps these to status codes."""


class IllegalTransitionError(WorkflowError):
    """The move is not in LEGAL_TRANSITIONS. Maps to 409 Conflict."""

    def __init__(self, current: ComplaintStatus, target: ComplaintStatus) -> None:
        self.current = current
        self.target = target
        allowed = sorted(s.value for s in allowed_from(current))
        super().__init__(
            f"Cannot move a complaint from '{current.value}' to '{target.value}'. "
            + (
                f"Allowed from '{current.value}': {', '.join(allowed)}."
                if allowed
                else f"'{current.value}' is a terminal status."
            )
        )


class PreconditionError(WorkflowError):
    """The move is legal in the abstract, but this complaint is not ready for
    it. Maps to 409 Conflict."""


class ReasonRequiredError(WorkflowError):
    """A backward transition was attempted without justification. Maps to 422."""

    def __init__(self, current: ComplaintStatus, target: ComplaintStatus) -> None:
        self.current = current
        self.target = target
        super().__init__(
            f"Returning a complaint from '{current.value}' to '{target.value}' requires a reason."
        )


def allowed_from(status: ComplaintStatus) -> frozenset[ComplaintStatus]:
    """Every status reachable from `status` in one legal move."""
    return LEGAL_TRANSITIONS.get(status, frozenset())


def is_legal(current: ComplaintStatus, target: ComplaintStatus) -> bool:
    """True if this exact move appears in the table."""
    return target in allowed_from(current)


def is_terminal(status: ComplaintStatus) -> bool:
    """True if nothing may follow. Only `closed` qualifies."""
    return not allowed_from(status)


def is_backward(current: ComplaintStatus, target: ComplaintStatus) -> bool:
    """True if the move regresses the complaint's position in the lifecycle."""
    return _ORDER[target] < _ORDER[current]


def permissions_for_target(target: ComplaintStatus) -> tuple[Permission, ...]:
    """Permissions the caller must hold to move a complaint *into* `target`.

    Returned as a tuple rather than checked here so the API layer can report
    every missing permission at once, in the same shape `deps.require()` uses.
    """
    extra = _EXTRA_PERMISSION.get(target)
    return (Permission.WORKFLOW_TRANSITION, extra) if extra else (Permission.WORKFLOW_TRANSITION,)


def requires_reason(current: ComplaintStatus, target: ComplaintStatus) -> bool:
    """True if this move may not be recorded without an explanation.

    Only returns need one. A complaint moving forward is the process working;
    a complaint moving back is the process being overridden, and the trail has
    to say why.
    """
    return is_backward(current, target)


@dataclass(frozen=True)
class TransitionOption:
    """One legal next step, described for a client that must render buttons."""

    to_status: ComplaintStatus
    requires_reason: bool
    required_permissions: tuple[Permission, ...]
    is_backward: bool


def options_from(status: ComplaintStatus) -> list[TransitionOption]:
    """Every legal next step from `status`, in lifecycle order."""
    return [
        TransitionOption(
            to_status=target,
            requires_reason=requires_reason(status, target),
            required_permissions=permissions_for_target(target),
            is_backward=is_backward(status, target),
        )
        for target in sorted(allowed_from(status), key=lambda s: _ORDER[s])
    ]


def record_creation(db: Session, complaint: Complaint, actor: User | None) -> StatusTransition:
    """Log the complaint's arrival into `new`.

    Written at creation so the timeline starts at the beginning. `from_status`
    is null, which is what distinguishes this row from a real move.
    """
    entry = StatusTransition(
        complaint=complaint,
        from_status=None,
        to_status=ComplaintStatus.NEW,
        changed_by_id=actor.id if actor else None,
        reason=None,
    )
    db.add(entry)
    return entry


def transition(
    db: Session,
    complaint: Complaint,
    target: ComplaintStatus,
    actor: User | None,
    reason: str | None = None,
) -> StatusTransition:
    """Move a complaint to `target`, or raise.

    Validates legality and the reason requirement, mutates the complaint, and
    appends the timeline row. Permission is checked by the caller, because the
    permission needed depends on the target - see `permissions_for_target`.

    Does not commit: the caller owns the transaction boundary, so the status
    change and the timeline row land in the same flush and the audit listener
    sees them together.
    """
    current = complaint.status

    if not is_legal(current, target):
        raise IllegalTransitionError(current, target)

    cleaned = reason.strip() if reason else None
    if requires_reason(current, target) and not cleaned:
        raise ReasonRequiredError(current, target)

    # An investigation with nobody responsible for it is not an investigation,
    # and "unassigned" is how complaints quietly age past their due date. The
    # assignment is therefore a precondition of entering the stage, not an
    # afterthought once it has started.
    if target is ComplaintStatus.INVESTIGATION and complaint.assigned_investigator_id is None:
        raise PreconditionError(
            "A complaint cannot enter investigation with no investigator assigned. "
            "Set assigned_investigator_id first."
        )

    complaint.status = target

    # closed_at is stored rather than derived because "when was this signed off"
    # is asked of the record far more often than the timeline is walked.
    if target is ComplaintStatus.CLOSED:
        complaint.closed_at = datetime.now(UTC)

    entry = StatusTransition(
        complaint=complaint,
        from_status=current,
        to_status=target,
        changed_by_id=actor.id if actor else None,
        reason=cleaned,
    )
    db.add(entry)
    return entry
