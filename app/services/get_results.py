from sqlalchemy.ext.asyncio import AsyncSession

from app.models.submission import Submission
from app.models.user import User
from app.crud.submission_repository import (
    SubmissionRepository,
)


class SubmissionNotFoundError(Exception):
    """`submission_id` does not exist (router: 404)."""


class NotSubmissionOwnerError(Exception):
    """Caller is neither the owner nor an admin (router: 403)."""


async def get_submission(
    session: AsyncSession, submission_id: int, current_user: User
) -> Submission:
    """Return one submission with its per-question breakdown.

    Raises `SubmissionNotFoundError` (404) or, for a non-admin caller who
    does not own the submission, `NotSubmissionOwnerError` (403) — **before**
    any of the submission's data has been queried (CRIT-2).
    """
    submission_repo = SubmissionRepository(session)

    # Step 1 (CRIT-2): fetch the OWNER ONLY. No score, no answers, nothing
    # that could leak if the caller turns out to be unauthorised.
    owner_user_id = await submission_repo.get_owner_user_id(submission_id)

    if owner_user_id is None:
        raise SubmissionNotFoundError(submission_id)

    if current_user.role != "admin" and owner_user_id != current_user.id:
        raise NotSubmissionOwnerError(submission_id)

    # Step 2: authorised — only now is any result data read.
    submission = await submission_repo.get_by_id_with_answers(submission_id)
    if submission is None:  # deleted between the two queries
        raise SubmissionNotFoundError(submission_id)
    return submission


async def list_submissions_for_exam(
    session: AsyncSession, exam_id: int
) -> list[Submission]:
    """Every submission for `exam_id`, with answers and owner eager-loaded.

    Admin-only; the router enforces that with `require_role("admin")`, so no
    per-row ownership check is needed here.

    WARN-4: exactly two queries regardless of the number of submissions —
    one for the submissions (with `exam_assignment` joined in) and one
    `selectinload` for all their answers.
    """
    return await SubmissionRepository(session).list_for_exam(exam_id)
