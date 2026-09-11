"""Reference data: who complains, about what product, from which batch.

These three tables exist as real entities rather than free-text columns on the
complaint because the genuinely valuable queries are cross-complaint ones:
"every complaint against batch BMX-240602" is how a recall decision gets made,
and it is only reliable if the batch is a foreign key rather than a string a
user re-typed.

The complaint also keeps denormalised name/batch text alongside the foreign
keys. That is deliberate - see the note in models/complaint.py.
"""

from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import Date, Enum, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.complaint import Complaint
from app.schemas.enums import ComplaintSource, DosageForm, QuantityUnit


class Customer(Base, TimestampMixin):
    """A pharmacy, hospital, distributor or wholesaler."""

    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    customer_type: Mapped[ComplaintSource | None] = mapped_column(
        Enum(ComplaintSource, name="customer_type", native_enum=False, length=40)
    )
    contact_email: Mapped[str | None] = mapped_column(String(255))
    contact_phone: Mapped[str | None] = mapped_column(String(50))
    city: Mapped[str | None] = mapped_column(String(120))
    country: Mapped[str | None] = mapped_column(String(120))

    complaints: Mapped[list["Complaint"]] = relationship(back_populates="customer")

    def __repr__(self) -> str:
        return f"<Customer {self.name}>"


class Product(Base, TimestampMixin):
    """A finished drug product or API in the portfolio."""

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    generic_name: Mapped[str | None] = mapped_column(String(200))
    strength: Mapped[str | None] = mapped_column(String(100))
    dosage_form: Mapped[DosageForm | None] = mapped_column(
        Enum(DosageForm, name="dosage_form", native_enum=False, length=40)
    )
    product_code: Mapped[str | None] = mapped_column(String(60), unique=True, index=True)
    therapeutic_category: Mapped[str | None] = mapped_column(String(160))

    batches: Mapped[list["Batch"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    complaints: Mapped[list["Complaint"]] = relationship(back_populates="product")

    def __repr__(self) -> str:
        return f"<Product {self.name} {self.strength or ''}>".strip() + ">"


class Batch(Base, TimestampMixin):
    """A manufactured lot.

    Batch number is unique *per product*, not globally - two products may
    legitimately reuse a lot code, and a global unique constraint would reject
    valid data.
    """

    __tablename__ = "batches"
    __table_args__ = (UniqueConstraint("product_id", "batch_number", name="product_batch"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True, nullable=False
    )
    batch_number: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    manufacturing_date: Mapped[date | None] = mapped_column(Date)
    expiry_date: Mapped[date | None] = mapped_column(Date)
    quantity_produced: Mapped[float | None] = mapped_column(Numeric(14, 3))
    quantity_unit: Mapped[QuantityUnit | None] = mapped_column(
        Enum(QuantityUnit, name="quantity_unit", native_enum=False, length=30)
    )
    manufacturing_site: Mapped[str | None] = mapped_column(String(160))
    units_released: Mapped[int | None] = mapped_column(Integer)

    product: Mapped[Product] = relationship(back_populates="batches")
    complaints: Mapped[list["Complaint"]] = relationship(back_populates="batch")

    def __repr__(self) -> str:
        return f"<Batch {self.batch_number}>"
