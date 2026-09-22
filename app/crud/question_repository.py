from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.question import Question


class QuestionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_existing_ids(self, ids: list[int]) -> set[int]:
        result = await self._session.execute(
            select(Question.id).where(Question.id.in_(ids))
        )
        return set(result.scalars().all())

    async def list_all_with_options(self) -> list[Question]:
        result = await self._session.execute(
            select(Question).options(selectinload(Question.options))
        )
        return list(result.scalars().unique().all())

    def add(self, question: Question) -> None:
        self._session.add(question)
