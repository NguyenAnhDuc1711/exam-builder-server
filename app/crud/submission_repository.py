from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.models.exam import ExamAssignment
from app.models.submission import Answer, Submission


class SubmissionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_owner_user_id(self, submission_id: int) -> int | None:
        return (
            await self._session.execute(
                select(ExamAssignment.user_id)
                .select_from(Submission)
                .join(
                    ExamAssignment, ExamAssignment.id == Submission.exam_assignment_id
                )
                .where(Submission.id == submission_id)
            )
        ).scalar_one_or_none()

    async def get_by_id_with_answers(self, submission_id: int) -> Submission | None:
        return (
            await self._session.execute(
                select(Submission)
                .where(Submission.id == submission_id)
                .options(selectinload(Submission.answers))
            )
        ).scalar_one_or_none()

    async def list_for_exam(self, exam_id: int) -> list[Submission]:
        result = await self._session.execute(
            select(Submission)
            .join(ExamAssignment, ExamAssignment.id == Submission.exam_assignment_id)
            .where(ExamAssignment.exam_id == exam_id)
            .options(
                joinedload(Submission.exam_assignment),
                selectinload(Submission.answers),
            )
            .order_by(Submission.id)
        )
        return list(result.scalars().unique().all())

    def add_submission(self, submission: Submission) -> None:
        self._session.add(submission)

    def add_answer(self, answer: Answer) -> None:
        self._session.add(answer)
