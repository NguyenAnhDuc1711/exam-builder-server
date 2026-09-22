from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import hash_password
from app.models.user import User
from app.crud.user_repository import UserRepository


class EmailAlreadyExistsError(Exception):
    """Raised when `email` already belongs to another user row."""


async def create_user(
    session: AsyncSession, email: str, password: str, role: str = "user"
) -> User:
    user_repo = UserRepository(session)

    existing = await user_repo.get_by_email(email)
    if existing is not None:
        raise EmailAlreadyExistsError(email)

    user = User(email=email, password_hash=hash_password(password), role=role)
    user_repo.add(user)
    await session.commit()
    return user
