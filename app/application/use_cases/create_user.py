"""Use case: admin-created user accounts (FR-2).

There is no public sign-up anywhere in the API (T003/T010 decision) — this
is the only path that brings a `user` account into existence. `role` is a
parameter here for testability, but the API surface (T010's router) never
lets the caller set it: every account created through `POST /users` gets
`role="user"`, so an admin cannot mint another admin through this endpoint
in v1 (avoids uncontrolled privilege escalation).
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.infrastructure.db.models.user import User


class EmailAlreadyExistsError(Exception):
    """Raised when `email` already belongs to another user row."""


async def create_user(
    session: AsyncSession, email: str, password: str, role: str = "user"
) -> User:
    """Create and persist a new user, hashing `password` first.

    Raises `EmailAlreadyExistsError` if `email` is already taken. Commits on
    success (this use case owns its transaction, same as `/auth/login`).

    Note: the uniqueness check-then-insert is not atomic. `user.email` has a
    DB-level unique index, so a true race would surface as an `IntegrityError`
    from `commit()` rather than this exception — acceptable for v1 single
    -admin usage, same class of gap as T003's documented concurrency notes.
    """
    existing = (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()
    if existing is not None:
        raise EmailAlreadyExistsError(email)

    user = User(email=email, password_hash=hash_password(password), role=role)
    session.add(user)
    await session.commit()
    return user
