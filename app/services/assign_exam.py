"""Use case: admin assigns an existing exam to an existing user (FR-5).

Both existence checks (exam, user) run before any insert. The
`(exam_id, user_id)` uniqueness rule is *not* re-checked with a SELECT
here — it relies on the DB-level `UniqueConstraint` T002 already put on
`exam_assignment` (`uq_exam_assignment_exam_id_user_id`). A duplicate
assignment therefore surfaces as an `IntegrityError` from `commit()`,
which is caught here and translated to `DuplicateAssignmentError` — same
check-then-insert-is-not-atomic trade-off `create_user` documents for
email uniqueness.
"""

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
    """Assign `exam_id` to `user_id`.

    Raises `ExamNotFoundError` if `exam_id` doesn't exist, `UserNotFoundError`
    if `user_id` doesn't exist or is not `role="user"` (an admin is not a
    valid assignment target), or `DuplicateAssignmentError` if this exam is
    already assigned to this user. All three are mapped to HTTP responses
    by the router (404, 404, 409 respectively).
    """
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
