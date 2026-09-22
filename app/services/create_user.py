"""Use case: create a `user` account (FR-2).

Shared by `POST /users` (admin-provisioned) and `POST /auth/register`
(public self-service). `role` is a parameter here for testability, but
neither route lets the caller set it: both always pass `role="user"`, so
nobody can mint an admin through this path (avoids uncontrolled privilege
escalation).
"""

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.user import User
from app.crud.user_repository import UserRepository


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
    user_repo = UserRepository(session)

    existing = await user_repo.get_by_email(email)
    if existing is not None:
        raise EmailAlreadyExistsError(email)

    user = User(email=email, password_hash=hash_password(password), role=role)
    user_repo.add(user)
    await session.commit()
    return user
