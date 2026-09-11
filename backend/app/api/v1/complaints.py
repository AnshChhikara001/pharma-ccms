"""Complaint endpoints: CRUD, search and the lifecycle.

The handlers here are deliberately thin. Persistence and search live in
`services/complaints.py`, lifecycle rules in `services/workflow.py`, and the
audit trail writes itself from SQLAlchemy events. What is left in this module is
the part that genuinely belongs to HTTP: resolving the complaint or returning
404, checking the permissions this particular request needs, and translating
domain errors into the status codes a client can act on.

    409  the request conflicts with the complaint's current state
    422  the request is well-formed but the result would be invalid
    403  the caller may not do this
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require
from app.core.rbac import Permission, has_permission
from app.models.complaint import Complaint
from app.models.investigation import StatusTransition
from app.models.user import User
from app.schemas.complaint import (
    ComplaintCreate,
    ComplaintFilters,
    ComplaintListItem,
    ComplaintPage,
    ComplaintRead,
    ComplaintUpdate,
    StatusTransitionRead,
    TransitionRequest,
)
from app.schemas.enums import ComplaintStatus
from app.services import complaints as service
from app.services import workflow

router = APIRouter()


def _get_or_404(db: Session, complaint_id: int) -> Complaint:
    complaint = db.get(Complaint, complaint_id)
    if complaint is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Complaint {complaint_id} not found",
        )
    return complaint


def _transition_read(entry: StatusTransition) -> StatusTransitionRead:
    """Flatten the actor's name into the timeline row.

    Resolved here rather than in the schema so the contract stays free of ORM
    knowledge, and so the timeline renders without a second request per row.
    """
    return StatusTransitionRead(
        id=entry.id,
        complaint_id=entry.complaint_id,
        from_status=entry.from_status,
        to_status=entry.to_status,
        changed_by_id=entry.changed_by_id,
        changed_by_name=entry.changed_by.full_name if entry.changed_by else None,
        reason=entry.reason,
        created_at=entry.created_at,
    )


def _assert_assignable(db: Session, investigator_id: int | None) -> None:
    """A complaint may only be assigned to someone who can actually work it.

    Without this, an assignment to a viewer - or to a deactivated account -
    looks successful and then sits in the queue with nobody able to progress it.
    """
    if investigator_id is None:
        return

    assignee = db.get(User, investigator_id)
    if assignee is None or not assignee.is_active:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"No active user with id {investigator_id}",
        )

    if not has_permission(assignee.role, Permission.INVESTIGATION_WRITE):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"{assignee.full_name} holds the '{assignee.role.value}' role, which "
                f"cannot carry out investigations"
            ),
        )


@router.get("", response_model=ComplaintPage, summary="Search complaints")
def list_complaints(
    filters: Annotated[ComplaintFilters, Query()],
    db: Session = Depends(get_db),
    _: User = Depends(require(Permission.COMPLAINT_READ)),
) -> ComplaintPage:
    """The complaint queue, filtered and paged.

    Every filter is optional and they compose; `batch_number` is the one that
    answers the recall question - every complaint logged against a given lot.
    """
    items, total = service.list_complaints(db, filters)
    pages = -(-total // filters.page_size)  # ceiling division
    return ComplaintPage(
        items=[ComplaintListItem.model_validate(c) for c in items],
        total=total,
        page=filters.page,
        page_size=filters.page_size,
        pages=pages,
    )


@router.post(
    "",
    response_model=ComplaintRead,
    status_code=status.HTTP_201_CREATED,
    summary="Log a complaint",
)
def create_complaint(
    payload: ComplaintCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require(Permission.COMPLAINT_CREATE)),
) -> Complaint:
    """Create a complaint in `new`, with its reference code and timeline started.

    Assigning an investigator at intake is allowed but needs the same permission
    a later reassignment does.
    """
    if payload.assigned_investigator_id is not None:
        if not has_permission(user.role, Permission.COMPLAINT_ASSIGN):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Role '{user.role.value}' lacks required permission: "
                    f"{Permission.COMPLAINT_ASSIGN.value}"
                ),
            )
        _assert_assignable(db, payload.assigned_investigator_id)

    return service.create_complaint(db, payload, user)


@router.get("/{complaint_id}", response_model=ComplaintRead, summary="Get a complaint")
def get_complaint(
    complaint_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require(Permission.COMPLAINT_READ)),
) -> Complaint:
    return _get_or_404(db, complaint_id)


@router.patch("/{complaint_id}", response_model=ComplaintRead, summary="Update a complaint")
def update_complaint(
    complaint_id: int,
    payload: ComplaintUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require(Permission.COMPLAINT_UPDATE)),
) -> Complaint:
    """Partial update. Fields not mentioned are not touched.

    Two extra rules are enforced here rather than in the service, because both
    are about *who is asking*:

    * Changing the assigned investigator additionally requires COMPLAINT_ASSIGN.
      `assigned_investigator_id` is an editable field like any other, so without
      this an investigator holding only COMPLAINT_UPDATE could reassign their
      own work and the separate permission would mean nothing.
    * A closed complaint is a signed-off record and is not editable. Reopening
      is deliberately impossible - see services/workflow.py.
    """
    complaint = _get_or_404(db, complaint_id)

    if complaint.status is ComplaintStatus.CLOSED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(f"Complaint {complaint.reference_code} is closed and can no longer be edited."),
        )

    changes = payload.model_dump(exclude_unset=True)

    if "assigned_investigator_id" in changes:
        if not has_permission(user.role, Permission.COMPLAINT_ASSIGN):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=(
                    f"Role '{user.role.value}' lacks required permission: "
                    f"{Permission.COMPLAINT_ASSIGN.value}"
                ),
            )
        _assert_assignable(db, changes["assigned_investigator_id"])

    try:
        return service.apply_update(db, complaint, payload)
    except service.ComplaintValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


@router.delete(
    "/{complaint_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a complaint",
)
def delete_complaint(
    complaint_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require(Permission.COMPLAINT_DELETE)),
) -> Response:
    """Delete an untriaged complaint - a duplicate or a mis-entry.

    Only possible while the complaint is still `new`. Anything further along has
    become part of the quality record and must be closed with a reason instead.
    The audit trail keeps a full snapshot of whatever is removed.
    """
    complaint = _get_or_404(db, complaint_id)

    if not service.is_deletable(complaint):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Complaint {complaint.reference_code} is in '{complaint.status.value}' "
                f"and can no longer be deleted. Close it with a reason instead."
            ),
        )

    service.delete_complaint(db, complaint)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── Lifecycle ─────────────────────────────────────────────────────────────────


@router.post(
    "/{complaint_id}/transition",
    response_model=ComplaintRead,
    summary="Move a complaint through the workflow",
)
def transition_complaint(
    complaint_id: int,
    payload: TransitionRequest,
    db: Session = Depends(get_db),
    user: User = Depends(require(Permission.WORKFLOW_TRANSITION)),
) -> Complaint:
    """Advance or return a complaint.

    Legality comes from the table in `services/workflow.py`; this handler only
    supplies the permission check that depends on the *target* - closing needs
    WORKFLOW_CLOSE, which only QA managers and admins hold.
    """
    complaint = _get_or_404(db, complaint_id)

    missing = [
        p
        for p in workflow.permissions_for_target(payload.to_status)
        if not has_permission(user.role, p)
    ]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=(
                f"Role '{user.role.value}' lacks required permission: "
                f"{', '.join(sorted(p.value for p in missing))}"
            ),
        )

    try:
        workflow.transition(db, complaint, payload.to_status, user, payload.reason)
    except workflow.ReasonRequiredError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    except workflow.WorkflowError as exc:
        # IllegalTransitionError and PreconditionError both mean "not from here".
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc

    db.commit()
    db.refresh(complaint)
    return complaint


@router.get(
    "/{complaint_id}/transitions",
    response_model=list[StatusTransitionRead],
    summary="Complaint timeline",
)
def complaint_timeline(
    complaint_id: int,
    db: Session = Depends(get_db),
    _: User = Depends(require(Permission.COMPLAINT_READ)),
) -> list[StatusTransitionRead]:
    """Every status change, oldest first. The first row records creation and has
    a null `from_status`."""
    _get_or_404(db, complaint_id)
    return [_transition_read(entry) for entry in service.timeline(db, complaint_id)]
