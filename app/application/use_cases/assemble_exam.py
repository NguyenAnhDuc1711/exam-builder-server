"""Use case: admin assembles an exam from question bank entries (FR-4).

WARN-1 fix (baked into 012.md): every `question_id` must exist in the
question bank before ANY row is written. Existence is checked with a
single `SELECT id FROM question WHERE id IN (...)`, compared as a set
against the input set — not one query per id — and if anything is
missing, `MissingQuestionsError` is raised *before* `session.add` is ever
called. No exam/exam_question row is created on failure, so there is
nothing to roll back.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.models.exam import Exam, ExamQuestion
from app.infrastructure.db.models.question import Question


class MissingQuestionsError(Exception):
    """One or more `question_ids` do not exist in the question bank."""

    def __init__(self, missing_ids: list[int]):
        self.missing_ids = missing_ids
        super().__init__(f"Unknown question ids: {missing_ids}")


async def create_exam(
    session: AsyncSession, title: str, question_ids: list[int]
) -> Exam:
    """Create an exam from an ordered list of question ids.

    `question_ids` order is preserved as `ExamQuestion.order` (0-based).
    Raises `MissingQuestionsError` (mapped to 404 by the router) if any id
    in `question_ids` does not exist in the question bank — validation
    runs entirely before any row is added to the session.
    """
    existing_ids = set(
        (
            await session.execute(
                select(Question.id).where(Question.id.in_(question_ids))
            )
        )
        .scalars()
        .all()
    )
    missing_ids = sorted(set(question_ids) - existing_ids)
    if missing_ids:
        raise MissingQuestionsError(missing_ids)

    exam = Exam(title=title)
    exam.exam_questions = [
        ExamQuestion(question_id=question_id, order=order)
        for order, question_id in enumerate(question_ids)
    ]
    session.add(exam)
    await session.commit()
    return exam
