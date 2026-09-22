from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_email(self, email: str) -> User | None:
        return (
            await self._session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()

    async def get_by_id(self, user_id: int) -> User | None:
        return await self._session.get(User, user_id)

    def add(self, user: User) -> None:
        self._session.add(user)
