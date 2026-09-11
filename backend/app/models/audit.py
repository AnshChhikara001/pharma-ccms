"""The audit trail.

21 CFR Part 11 expects a computer-generated, time-stamped record of who changed
what and when. The operative word is *computer-generated*: an audit trail a
developer has to remember to write is one that will eventually be incomplete.

So entries are produced by SQLAlchemy session events in `app/services/audit.py`,
not by calls scattered through the endpoints. Adding a new endpoint that mutates
a complaint cannot silently skip the audit trail, because no endpoint writes to
it in the first place.
"""

from typing import TYPE_CHECKING, Any

from sqlalchemy import JSON, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User
from app.schemas.enums import AuditAction


class AuditEntry(Base, TimestampMixin):
    """One recorded change.

    Deliberately polymorphic (`entity_type` + `entity_id` rather than a real
    foreign key): the trail must survive deletion of the row it describes. A
    proper FK with ON DELETE CASCADE would erase exactly the history an auditor
    came to read.
    """

    __tablename__ = "audit_entries"

    id: Mapped[int] = mapped_column(primary_key=True)

    entity_type: Mapped[str] = mapped_column(String(60), index=True, nullable=False)
    entity_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)

    action: Mapped[AuditAction] = mapped_column(
        Enum(AuditAction, name="audit_action", native_enum=False, length=40), nullable=False
    )

    # {field: {"old": ..., "new": ...}} for updates; the created row for inserts.
    changes: Mapped[dict[str, Any] | None] = mapped_column(JSON)

    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    # Kept as text as well as an FK: if the user record is later removed, the
    # trail must still say who acted.
    actor_email: Mapped[str | None] = mapped_column(String(255))
    summary: Mapped[str | None] = mapped_column(String(500))

    actor: Mapped["User | None"] = relationship()

    def __repr__(self) -> str:
        return f"<AuditEntry {self.entity_type}#{self.entity_id} {self.action}>"
