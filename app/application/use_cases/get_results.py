"""Use case: reading submission results (FR-7).

**CRIT-2 — ownership is checked before any submission data is read.**
`get_submission` deliberately runs in two steps: the first query selects
*only* `exam_assignment.user_id` — the owner — and nothing else. The
403/404 decision is made from that single scalar. The submission's score,
answers and breakdown are only fetched by the *second* query, which is
unreachable for a caller that failed the check. There is therefore no
moment at which result data exists in memory for an unauthorised caller,
and no "load then filter" ordering mistake is possible.

**WARN-4 — `list_submissions_for_exam` does not N+1.** It eager-loads
`Submission.answers` (`selectinload`) and `Submission.exam_assignment`
(`joinedload`), so the query count is a constant 2 no matter how many
submissions the exam has.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from app.infrastructure.db.models.exam import ExamAssignment
from app.infrastructure.db.models.submission import Submission
from app.infrastructure.db.models.user import User


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
    # Step 1 (CRIT-2): fetch the OWNER ONLY. No score, no answers, nothing
    # that could leak if the caller turns out to be unauthorised.
    owner_user_id = (
        await session.execute(
            select(ExamAssignment.user_id)
            .select_from(Submission)
            .join(ExamAssignment, ExamAssignment.id == Submission.exam_assignment_id)
            .where(Submission.id == submission_id)
        )
    ).scalar_one_or_none()

    if owner_user_id is None:
        raise SubmissionNotFoundError(submission_id)

    if current_user.role != "admin" and owner_user_id != current_user.id:
        raise NotSubmissionOwnerError(submission_id)

    # Step 2: authorised — only now is any result data read.
    submission = (
        await session.execute(
            select(Submission)
            .where(Submission.id == submission_id)
            .options(selectinload(Submission.answers))
        )
    ).scalar_one_or_none()
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
    result = await session.execute(
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
