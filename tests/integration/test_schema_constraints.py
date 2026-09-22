"""DB-level constraint tests (require a running PostgreSQL).

NOTE (T002): written without a Python/Docker runtime available in the
authoring environment — unexecuted, see the T002 handoff.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models import (
    Exam,
    ExamAssignment,
    Option,
    Question,
    Submission,
    User,
)


async def _seed_exam_and_user(session):
    user = User(email="student@example.com", password_hash="hashed", role="user")
    exam = Exam(title="Midterm")
    session.add_all([user, exam])
    await session.commit()
    return user, exam


async def test_duplicate_exam_assignment_is_rejected(session):
    """FR-5: UNIQUE(exam_id, user_id) on exam_assignment."""
    user, exam = await _seed_exam_and_user(session)

    session.add(ExamAssignment(exam_id=exam.id, user_id=user.id))
    await session.commit()

    session.add(ExamAssignment(exam_id=exam.id, user_id=user.id))
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


async def test_second_submission_for_same_assignment_is_rejected(session):
    """FR-6: UNIQUE(exam_assignment_id) on submission — single attempt."""
    user, exam = await _seed_exam_and_user(session)
    assignment = ExamAssignment(exam_id=exam.id, user_id=user.id)
    session.add(assignment)
    await session.commit()

    session.add(Submission(exam_assignment_id=assignment.id, score=0))
    await session.commit()

    session.add(Submission(exam_assignment_id=assignment.id, score=0))
    with pytest.raises(IntegrityError):
        await session.commit()
    await session.rollback()


async def test_deleting_a_question_cascades_to_its_options(session):
    question = Question(
        text="2 + 2 = ?",
        options=[
            Option(text="4", is_correct=True),
            Option(text="5", is_correct=False),
        ],
    )
    session.add(question)
    await session.commit()
    question_id = question.id

    await session.delete(question)
    await session.commit()

    result = await session.execute(
        select(Option).where(Option.question_id == question_id)
    )
    assert result.scalars().all() == []
