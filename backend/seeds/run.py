"""Seed entrypoint.

    python -m seeds.run

Safe to re-run. Later phases add reference data and complaints here.
"""

import sys

from app.core.database import SessionLocal
from seeds.users import DEMO_PASSWORD, seed_users


def main() -> int:
    with SessionLocal() as db:
        users = seed_users(db)

    print(f"Seeded {len(users)} demo users (password for all: {DEMO_PASSWORD})\n")
    print(f"  {'ROLE':<20} {'EMAIL':<34} NAME")
    for user in users:
        print(f"  {user.role.value:<20} {user.email:<34} {user.full_name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
