"""Load the demo complaint corpus through the real application pathways.

Every complaint in `seeds/complaint_data.py` is created via
`services.complaints.create_complaint` and walked to its target status via
`services.workflow.transition` - never inserted as a bare row. That is
deliberate: demo data built by skipping the service layer would skip reference
code allocation, reference-data linking and the audit trail along with it, and
a reviewer clicking into a seeded complaint would see a timeline that the
application itself could never have produced.

Idempotency here means something different from `seeds/users.py` and
`seeds/reference.py`. A complaint is a transactional record, not master data;
re-running the seed must not silently rewrite one's history by re-driving it
through the workflow a second time. Instead, each seed is matched against an
existing complaint by its description - unique by construction in the corpus -
and skipped entirely if found.
"""

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.complaint import Complaint
from app.models.user import User
from app.schemas.complaint import ComplaintCreate
from app.schemas.enums import ComplaintStatus, UserRole
from app.services import complaints as complaint_service
from app.services import workflow
from seeds.complaint_data import COMPLAINT_SEEDS, ComplaintSeed

_LIFECYCLE_INDEX = {status: i for i, status in enumerate(workflow.LIFECYCLE)}
_INVESTIGATION_INDEX = _LIFECYCLE_INDEX[ComplaintStatus.INVESTIGATION]


def _existing(db: Session, description: str) -> Complaint | None:
    return db.execute(
        select(Complaint).where(Complaint.description == description)
    ).scalar_one_or_none()


def _create_from_seed(
    db: Session, seed: ComplaintSeed, actor: User, investigator: User
) -> Complaint:
    """Log the complaint as it would have arrived: with a real, dated payload.

    An investigator is attached at intake when the seed calls for one. The
    lifecycle stage the complaint ends up at may still require an investigator
    even when the seed does not flag one - see `_walk_to_target`.
    """
    complaint_date = date.today() - timedelta(days=seed.days_ago)
    due_date = (
        complaint_date + timedelta(days=seed.due_in_days) if seed.due_in_days is not None else None
    )

    payload = ComplaintCreate(
        source=seed.source,
        customer_name=seed.customer_name,
        customer_contact=seed.customer_contact,
        reporter_name=seed.reporter_name,
        product_name=seed.product_name,
        product_strength=seed.product_strength,
        dosage_form=seed.dosage_form,
        batch_number=seed.batch_number,
        quantity_affected=seed.quantity_affected,
        quantity_unit=seed.quantity_unit,
        complaint_type=seed.complaint_type,
        complaint_date=complaint_date,
        description=seed.description,
        severity=seed.severity,
        priority=seed.priority,
        assigned_investigator_id=investigator.id if seed.investigator else None,
        due_date=due_date,
    )
    return complaint_service.create_complaint(db, payload, actor)


def _walk_to_target(
    db: Session, complaint: Complaint, target: ComplaintStatus, actor: User, investigator: User
) -> None:
    """Advance a freshly created complaint to `target` along the happy path.

    Every seeded complaint's target lies forward of `new`, so no move here is
    a return and none needs a reason. A complaint bound for `investigation` or
    beyond gets an investigator assigned first regardless of the seed's own
    `investigator` flag - the workflow engine will not admit one without it,
    and demo data is not exempt from the rule it exists to demonstrate.
    """
    target_index = _LIFECYCLE_INDEX[target]

    if target_index >= _INVESTIGATION_INDEX and complaint.assigned_investigator_id is None:
        complaint.assigned_investigator_id = investigator.id

    for status in workflow.LIFECYCLE[1 : target_index + 1]:
        workflow.transition(db, complaint, status, actor)

    db.commit()
    db.refresh(complaint)


def seed_complaints(db: Session, users: dict[UserRole, User]) -> list[Complaint]:
    """Create every complaint in the demo corpus, in declaration order.

    Acts as the complaint officer for intake and as the QA manager for every
    lifecycle move, since QA manager holds every permission a transition might
    need (including closure) and that keeps the loader from having to reason
    about which role may make which move - `tests/test_workflow.py` already
    covers that policy.
    """
    officer = users[UserRole.COMPLAINT_OFFICER]
    qa_manager = users[UserRole.QA_MANAGER]
    investigator = users[UserRole.INVESTIGATOR]

    complaints: list[Complaint] = []

    for seed in COMPLAINT_SEEDS:
        complaint = _existing(db, seed.description)
        if complaint is None:
            complaint = _create_from_seed(db, seed, officer, investigator)
            _walk_to_target(db, complaint, seed.target_status, qa_manager, investigator)

        complaints.append(complaint)

    return complaints
