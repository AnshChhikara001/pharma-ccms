"""Seed one demo user per role.

Idempotent: re-running updates the existing rows rather than failing on the
unique email constraint, so `python -m seeds.run` is safe to repeat.

The shared demo password is fine for a demo system and nowhere near acceptable
for production; the README says so plainly.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.user import User
from app.schemas.enums import UserRole

DEMO_PASSWORD = "Demo@12345"

DEMO_USERS: list[dict[str, object]] = [
    {
        "email": "admin@pharmaco.com",
        "full_name": "Arjun Mehta",
        "role": UserRole.ADMIN,
        "department": "IT & Systems",
    },
    {
        "email": "qa.manager@pharmaco.com",
        "full_name": "Dr. Priya Sharma",
        "role": UserRole.QA_MANAGER,
        "department": "Quality Assurance",
    },
    {
        "email": "complaint.officer@pharmaco.com",
        "full_name": "Rahul Verma",
        "role": UserRole.COMPLAINT_OFFICER,
        "department": "Customer Quality",
    },
    {
        "email": "investigator@pharmaco.com",
        "full_name": "Sneha Iyer",
        "role": UserRole.INVESTIGATOR,
        "department": "Quality Control Laboratory",
    },
    {
        "email": "viewer@pharmaco.com",
        "full_name": "Vikram Nair",
        "role": UserRole.VIEWER,
        "department": "Regulatory Affairs",
    },
]


def seed_users(db: Session) -> list[User]:
    """Create or refresh the demo users. Returns them in role order."""
    created: list[User] = []

    for spec in DEMO_USERS:
        email = str(spec["email"])
        user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()

        if user is None:
            user = User(
                email=email,
                full_name=str(spec["full_name"]),
                hashed_password=hash_password(DEMO_PASSWORD),
                role=spec["role"],  # type: ignore[arg-type]
                department=str(spec["department"]),
                is_active=True,
            )
            db.add(user)
        else:
            user.full_name = str(spec["full_name"])
            user.role = spec["role"]  # type: ignore[assignment]
            user.department = str(spec["department"])
            user.is_active = True

        created.append(user)

    db.commit()
    for user in created:
        db.refresh(user)
    return created
