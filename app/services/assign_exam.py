from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.exam import ExamAssignment
from app.crud.exam_assignment_repository import (
    ExamAssignmentRepository,
)
from app.crud.exam_repository import ExamRepository
from app.crud.user_repository import UserRepository


class ExamNotFoundError(Exception):
    """`exam_id` does not exist."""


class UserNotFoundError(Exception):
    """`user_id` does not exist, or exists but is not role='user'."""


class DuplicateAssignmentError(Exception):
    """This `(exam_id, user_id)` pair is already assigned."""


async def assign_exam(
    session: AsyncSession, exam_id: int, user_id: int
) -> ExamAssignment:
    exam = await ExamRepository(session).get_by_id(exam_id)
    if exam is None:
        raise ExamNotFoundError(exam_id)

    user = await UserRepository(session).get_by_id(user_id)
    if user is None or user.role != "user":
        raise UserNotFoundError(user_id)

    assignment = ExamAssignment(exam_id=exam_id, user_id=user_id)
    ExamAssignmentRepository(session).add(assignment)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise DuplicateAssignmentError(
            f"Exam {exam_id} is already assigned to user {user_id}"
        )
    return assignment
