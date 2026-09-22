"""One-off bootstrap: create the first admin account.

`POST /users` requires an existing admin token by design (no public sign-up —
see 010.md). Every environment needs exactly one manual bootstrap step before
that endpoint becomes usable at all. Run once per environment:

    SEED_ADMIN_EMAIL=admin@example.com SEED_ADMIN_PASSWORD=change-me \
        python -m scripts.seed_admin

Idempotent: does nothing (exit 0) if an account with that email already exists.
"""

import asyncio
import os
import sys

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.security import hash_password
from app.models.user import User


async def seed_admin(email: str, password: str) -> None:
    async with AsyncSessionLocal() as session:
        existing = await session.scalar(select(User).where(User.email == email))
        if existing is not None:
            print(f"Admin '{email}' already exists — nothing to do.")
            return

        admin = User(email=email, password_hash=hash_password(password), role="admin")
        session.add(admin)
        await session.commit()
        print(f"Created admin '{email}'.")


def main() -> None:
    email = os.environ.get("SEED_ADMIN_EMAIL")
    password = os.environ.get("SEED_ADMIN_PASSWORD")
    if not email or not password:
        print(
            "SEED_ADMIN_EMAIL and SEED_ADMIN_PASSWORD must both be set.",
            file=sys.stderr,
        )
        sys.exit(1)

    asyncio.run(seed_admin(email, password))


if __name__ == "__main__":
    main()
