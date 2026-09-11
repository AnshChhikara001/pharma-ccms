"""Investigation, root cause, CAPA and the status transition log.

These four tables are what turn a complaint record into a QMS. Each carries the
same structural theme: **who decided, when, and was it AI-suggested or
human-determined.** That last distinction is not decoration - a root cause the
AI proposed and a root cause a qualified investigator confirmed have entirely
different regulatory weight, and the schema refuses to blur them.
"""

from datetime import date, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.complaint import Complaint
    from app.models.user import User
from app.schemas.enums import ComplaintStatus


class Investigation(Base, TimestampMixin):
    """The investigation record for a complaint."""

    __tablename__ = "investigations"

    id: Mapped[int] = mapped_column(primary_key=True)
    complaint_id: Mapped[int] = mapped_column(
        ForeignKey("complaints.id", ondelete="CASCADE"), index=True, nullable=False
    )
    investigator_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )

    methodology: Mapped[str | None] = mapped_column(String(200))
    findings: Mapped[str | None] = mapped_column(Text)
    samples_examined: Mapped[str | None] = mapped_column(Text)
    batch_record_review: Mapped[str | None] = mapped_column(Text)

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    complaint: Mapped["Complaint"] = relationship(back_populates="investigations")
    investigator: Mapped["User | None"] = relationship()


class RootCause(Base, TimestampMixin):
    """A determined or proposed root cause.

    `is_ai_suggested` is the important column. An AI hypothesis may be stored
    here so an investigator can review it, but until a human sets
    `confirmed_by_id` it is explicitly not a determination.
    """

    __tablename__ = "root_causes"

    id: Mapped[int] = mapped_column(primary_key=True)
    complaint_id: Mapped[int] = mapped_column(
        ForeignKey("complaints.id", ondelete="CASCADE"), index=True, nullable=False
    )

    category: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    contributing_factors: Mapped[str | None] = mapped_column(Text)

    is_ai_suggested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    confirmed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    complaint: Mapped["Complaint"] = relationship(back_populates="root_causes")
    confirmed_by: Mapped["User | None"] = relationship()

    @property
    def is_confirmed(self) -> bool:
        """True only once a qualified human has signed off."""
        return self.confirmed_by_id is not None


class CAPA(Base, TimestampMixin):
    """A corrective or preventive action."""

    __tablename__ = "capas"

    id: Mapped[int] = mapped_column(primary_key=True)
    complaint_id: Mapped[int] = mapped_column(
        ForeignKey("complaints.id", ondelete="CASCADE"), index=True, nullable=False
    )

    # "corrective" fixes what happened; "preventive" stops recurrence. Kept as a
    # plain string rather than an enum because sites word these differently.
    action_type: Mapped[str] = mapped_column(String(20), nullable=False, default="corrective")
    description: Mapped[str] = mapped_column(Text, nullable=False)

    owner_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    due_date: Mapped[date | None] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="open")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Regulators care as much about whether the action worked as whether it was
    # done, so effectiveness review is a first-class field.
    effectiveness_check: Mapped[str | None] = mapped_column(Text)
    effectiveness_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    is_ai_suggested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    complaint: Mapped["Complaint"] = relationship(back_populates="capas")
    owner: Mapped["User | None"] = relationship()


class StatusTransition(Base, TimestampMixin):
    """One hop in the complaint lifecycle.

    Append-only. This table *is* the timeline the detail screen renders, and
    together with AuditEntry it answers "how did this complaint get here".
    """

    __tablename__ = "status_transitions"

    id: Mapped[int] = mapped_column(primary_key=True)
    complaint_id: Mapped[int] = mapped_column(
        ForeignKey("complaints.id", ondelete="CASCADE"), index=True, nullable=False
    )

    # Null on the very first transition, which records creation into NEW.
    from_status: Mapped[ComplaintStatus | None] = mapped_column(
        Enum(ComplaintStatus, name="from_status", native_enum=False, length=40)
    )
    to_status: Mapped[ComplaintStatus] = mapped_column(
        Enum(ComplaintStatus, name="to_status", native_enum=False, length=40), nullable=False
    )
    changed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reason: Mapped[str | None] = mapped_column(Text)

    complaint: Mapped["Complaint"] = relationship(back_populates="transitions")
    changed_by: Mapped["User | None"] = relationship()
