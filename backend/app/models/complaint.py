"""The complaint aggregate and everything hanging off it.

Column set mirrors `app/schemas/complaint.py` field for field. That duplication
is intentional and narrow: Pydantic owns validation and the wire format,
SQLAlchemy owns storage and relationships. They are kept in step by
`tests/test_model_contract_parity.py`, which fails if either side gains a field
the other lacks.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.investigation import CAPA, Investigation, RootCause, StatusTransition
    from app.models.reference import Batch, Customer, Product
    from app.models.user import User
from app.schemas.enums import (
    ComplaintSource,
    ComplaintStatus,
    ComplaintType,
    DocumentKind,
    DosageForm,
    Priority,
    QuantityUnit,
    Severity,
)


def _enum(enum_cls: type[Any], name: str, length: int = 40) -> Enum:
    """Store enums as VARCHAR rather than a native PG ENUM type.

    Native Postgres enums require an ALTER TYPE migration to add a value, which
    is a needless obstacle for a vocabulary that will grow. VARCHAR + a CHECK
    from SQLAlchemy gives the same safety with far cheaper evolution, and keeps
    SQLite (used in tests) behaviourally identical to Postgres.
    """
    return Enum(enum_cls, name=name, native_enum=False, length=length)


class Complaint(Base, TimestampMixin):
    """A customer complaint, from intake through closure."""

    __tablename__ = "complaints"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Human-facing identifier, e.g. CMP-2026-0042. Assigned on creation; this is
    # what appears in correspondence and regulatory filings, so it never changes.
    reference_code: Mapped[str] = mapped_column(String(30), unique=True, index=True, nullable=False)

    # ── 1. Origin & customer ────────────────────────────────────────────────
    source: Mapped[ComplaintSource | None] = mapped_column(
        _enum(ComplaintSource, "complaint_source")
    )
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id", ondelete="SET NULL"), index=True
    )
    # Denormalised alongside customer_id on purpose: AI extraction frequently
    # yields a customer name that matches no existing record. Losing it would
    # discard evidence, so the text is always kept and the FK is linked when a
    # confident match exists.
    customer_name: Mapped[str | None] = mapped_column(String(200), index=True)
    customer_contact: Mapped[str | None] = mapped_column(String(200))
    reporter_name: Mapped[str | None] = mapped_column(String(200))

    # ── 2. Product & batch ──────────────────────────────────────────────────
    product_id: Mapped[int | None] = mapped_column(
        ForeignKey("products.id", ondelete="SET NULL"), index=True
    )
    product_name: Mapped[str | None] = mapped_column(String(200), index=True)
    product_strength: Mapped[str | None] = mapped_column(String(100))
    dosage_form: Mapped[DosageForm | None] = mapped_column(_enum(DosageForm, "cmp_dosage_form"))
    batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("batches.id", ondelete="SET NULL"), index=True
    )
    batch_number: Mapped[str | None] = mapped_column(String(100), index=True)
    manufacturing_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    quantity_affected: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    quantity_unit: Mapped[QuantityUnit | None] = mapped_column(
        _enum(QuantityUnit, "cmp_quantity_unit", 30)
    )

    # ── 3. Complaint details ────────────────────────────────────────────────
    complaint_type: Mapped[ComplaintType | None] = mapped_column(
        _enum(ComplaintType, "complaint_type", 50)
    )
    complaint_date: Mapped[date | None] = mapped_column(Date, index=True)
    description: Mapped[str | None] = mapped_column(Text)

    # ── 4. Assessment & priority ────────────────────────────────────────────
    severity: Mapped[Severity | None] = mapped_column(_enum(Severity, "severity", 20), index=True)
    priority: Mapped[Priority | None] = mapped_column(_enum(Priority, "priority", 20))

    # ── Workflow ────────────────────────────────────────────────────────────
    status: Mapped[ComplaintStatus] = mapped_column(
        _enum(ComplaintStatus, "complaint_status"),
        nullable=False,
        default=ComplaintStatus.NEW,
        index=True,
    )
    assigned_investigator_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    due_date: Mapped[date | None] = mapped_column(Date, index=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    # ── Relationships ───────────────────────────────────────────────────────
    customer: Mapped["Customer | None"] = relationship(back_populates="complaints")
    product: Mapped["Product | None"] = relationship(back_populates="complaints")
    batch: Mapped["Batch | None"] = relationship(back_populates="complaints")

    assigned_investigator: Mapped["User | None"] = relationship(
        foreign_keys=[assigned_investigator_id]
    )
    created_by: Mapped["User | None"] = relationship(foreign_keys=[created_by_id])

    documents: Mapped[list["ComplaintDocument"]] = relationship(
        back_populates="complaint", cascade="all, delete-orphan"
    )
    ai_assessments: Mapped[list["AIAssessmentRecord"]] = relationship(
        back_populates="complaint", cascade="all, delete-orphan"
    )
    transitions: Mapped[list["StatusTransition"]] = relationship(
        back_populates="complaint",
        cascade="all, delete-orphan",
        order_by="StatusTransition.created_at",
    )
    investigations: Mapped[list["Investigation"]] = relationship(
        back_populates="complaint", cascade="all, delete-orphan"
    )
    root_causes: Mapped[list["RootCause"]] = relationship(
        back_populates="complaint", cascade="all, delete-orphan"
    )
    capas: Mapped[list["CAPA"]] = relationship(
        back_populates="complaint", cascade="all, delete-orphan"
    )

    @property
    def is_overdue(self) -> bool:
        """Past its due date and not yet closed.

        Computed rather than stored: a stored flag would need a scheduled job to
        stay truthful, and would be wrong between runs.
        """
        if self.due_date is None or self.status == ComplaintStatus.CLOSED:
            return False
        return self.due_date < date.today()

    def __repr__(self) -> str:
        return f"<Complaint {self.reference_code} {self.status}>"


class ComplaintDocument(Base, TimestampMixin):
    """An uploaded email, letter, photo or report attached to a complaint."""

    __tablename__ = "complaint_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    complaint_id: Mapped[int] = mapped_column(
        ForeignKey("complaints.id", ondelete="CASCADE"), index=True, nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[DocumentKind] = mapped_column(_enum(DocumentKind, "document_kind", 20))
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)

    # Text pulled out by the parser, cached so re-running extraction costs
    # nothing and so the document stays searchable after the file is archived.
    extracted_text: Mapped[str | None] = mapped_column(Text)
    uploaded_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))

    complaint: Mapped[Complaint] = relationship(back_populates="documents")


class AIAssessmentRecord(Base, TimestampMixin):
    """A stored AI assessment.

    Kept as an append-only history rather than a single mutable column: the
    assessment changes as fields are filled in, and a regulated system must be
    able to show what the AI advised *at the time* a decision was taken.
    """

    __tablename__ = "ai_assessments"

    id: Mapped[int] = mapped_column(primary_key=True)
    complaint_id: Mapped[int] = mapped_column(
        ForeignKey("complaints.id", ondelete="CASCADE"), index=True, nullable=False
    )

    # The full AIAssessment schema, stored verbatim. JSON rather than columns
    # because the shape is the AI layer's concern and will evolve; nothing in
    # the database queries inside it.
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)

    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(80), nullable=False)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer)
    completion_tokens: Mapped[int | None] = mapped_column(Integer)
    cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(10, 6))
    is_superseded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    complaint: Mapped[Complaint] = relationship(back_populates="ai_assessments")
