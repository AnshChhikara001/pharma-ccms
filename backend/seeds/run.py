"""Seed entrypoint.

    python -m seeds.run

Safe to re-run: users and reference data are created-or-updated, and complaints
are created-or-skipped by matching on description. See each module's docstring
for exactly what "idempotent" means there.
"""

import sys

from app.core.database import SessionLocal
from seeds.complaints import seed_complaints
from seeds.reference import seed_reference_data
from seeds.users import DEMO_PASSWORD, seed_users


def main() -> int:
    with SessionLocal() as db:
        users = seed_users(db)
        by_role = {user.role: user for user in users}

        customers, products, batches = seed_reference_data(db)
        complaints = seed_complaints(db, by_role)

    print(f"Seeded {len(users)} demo users (password for all: {DEMO_PASSWORD})\n")
    print(f"  {'ROLE':<20} {'EMAIL':<34} NAME")
    for user in users:
        print(f"  {user.role.value:<20} {user.email:<34} {user.full_name}")

    print(
        f"\nSeeded {len(customers)} customers, {len(products)} products, "
        f"{len(batches)} batches, {len(complaints)} complaints\n"
    )

    by_status: dict[str, int] = {}
    for complaint in complaints:
        by_status[complaint.status.value] = by_status.get(complaint.status.value, 0) + 1
    for status_value, count in sorted(by_status.items()):
        print(f"  {status_value:<24} {count}")

    overdue = sum(1 for c in complaints if c.is_overdue)
    print(f"\n  {'overdue':<24} {overdue}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
