from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.exam import Exam, ExamQuestion
from app.models.question import Option


class ExamRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_id(self, exam_id: int) -> Exam | None:
        return await self._session.get(Exam, exam_id)

    async def get_by_id_with_questions(self, exam_id: int) -> Exam | None:
        return (
            await self._session.execute(
                select(Exam)
                .where(Exam.id == exam_id)
                .options(selectinload(Exam.exam_questions))
            )
        ).scalar_one_or_none()

    async def get_grading_data(
        self, exam_id: int
    ) -> list[tuple[int, int | None, bool | None]]:
        rows = (
            await self._session.execute(
                select(ExamQuestion.question_id, Option.id, Option.is_correct)
                .select_from(ExamQuestion)
                .outerjoin(Option, Option.question_id == ExamQuestion.question_id)
                .where(ExamQuestion.exam_id == exam_id)
                .order_by(ExamQuestion.order, ExamQuestion.question_id, Option.id)
            )
        ).all()
        return [tuple(row) for row in rows]

    def add(self, exam: Exam) -> None:
        self._session.add(exam)
