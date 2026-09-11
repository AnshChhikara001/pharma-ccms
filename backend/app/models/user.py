"""System users and their roles."""

from sqlalchemy import Boolean, Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.schemas.enums import UserRole


class User(Base, TimestampMixin):
    """A person who can log in.

    `role` is a single value rather than a many-to-many permission set. A
    pharmaceutical QMS has a small, stable set of job functions, and the
    regulatory expectation is that responsibility is unambiguous - "who approved
    this" must have exactly one answer. A permission matrix would obscure that.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)

    # bcrypt hash. Never the password itself, and never logged.
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)

    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", native_enum=False, length=32),
        nullable=False,
        default=UserRole.VIEWER,
    )
    department: Mapped[str | None] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    def __repr__(self) -> str:
        return f"<User {self.email} role={self.role}>"
