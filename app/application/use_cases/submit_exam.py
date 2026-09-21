"""Use case: a user submits answers for an assigned exam (FR-6).

Two things in here are load-bearing and were called out as CRITICAL /
WARNING by plan-review — do not "simplify" them away:

**CRIT-1 — one transaction.** The `Submission` row and all its `Answer`
rows are inserted inside a single ``async with session.begin():`` block.
If *any* insert (or the final COMMIT) raises, the whole block is rolled
back, so the database can never end up holding a `Submission` without the
`Answer` rows that belong to it.

**WARN-2 — double submit is a 409, not a 500.** `submission.exam_assignment_id`
is UNIQUE (T002). That constraint — not an application-level "has this
already been submitted?" SELECT — is the source of truth for FR-6's
single-attempt rule, because two concurrent requests can both pass such a
SELECT before either commits. So the `IntegrityError` is caught and
translated into `AlreadySubmittedError`, which the router renders as a
clean 409.

Grading matches each submitted answer to its question **by `question_id`**,
never by position in the submitted list (`ExamQuestion.order` is a display
concern only).
"""

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.db.models.exam import ExamAssignment, ExamQuestion
from app.infrastructure.db.models.question import Option
from app.infrastructure.db.models.submission import Answer, Submission
from app.infrastructure.db.models.user import User


class AssignmentNotFoundError(Exception):
    """`exam_assignment_id` does not exist (router: 404)."""


class NotAssignmentOwnerError(Exception):
    """The assignment belongs to a different user (router: 403)."""


class InvalidAnswerError(Exception):
    """A `selected_option_id` is not an option of its question (router: 400)."""


class AlreadySubmittedError(Exception):
    """This assignment already has a submission (router: 409)."""


@dataclass(frozen=True)
class AnswerInput:
    question_id: int
    # None = the question was left unanswered; never scored as correct.
    selected_option_id: int | None = None


@dataclass(frozen=True)
class GradedAnswer:
    question_id: int
    selected_option_id: int | None
    is_correct: bool


@dataclass(frozen=True)
class SubmissionResult:
    submission_id: int
    score: int
    total_questions: int
    breakdown: list[GradedAnswer]


def grade(
    correct_option_by_question: dict[int, int | None],
    answers: Sequence[AnswerInput],
) -> list[GradedAnswer]:
    """Pure function — no I/O, so it is directly unit-testable (SC-2).

    `correct_option_by_question` maps every `question_id` **in the exam** to
    the id of its correct `Option` (or `None` when the question has no
    correct option, in which case nothing can score it as right). Its
    insertion order is the exam's question order, and the returned breakdown
    follows it.

    The exam — not the submitted payload — decides which questions are
    graded: a question the user skipped becomes an unanswered (`None`,
    `is_correct=False`) entry, and an answer for a `question_id` outside the
    exam is ignored, so extra/duplicate entries in the payload cannot
    inflate the score. If the payload repeats a `question_id`, the last
    occurrence wins.
    """
    submitted: dict[int, int | None] = {
        a.question_id: a.selected_option_id for a in answers
    }
    graded: list[GradedAnswer] = []
    for question_id, correct_option_id in correct_option_by_question.items():
        selected_option_id = submitted.get(question_id)
        graded.append(
            GradedAnswer(
                question_id=question_id,
                selected_option_id=selected_option_id,
                is_correct=(
                    selected_option_id is not None
                    and selected_option_id == correct_option_id
                ),
            )
        )
    return graded


async def submit_exam(
    session: AsyncSession,
    assignment_id: int,
    answers: Sequence[AnswerInput],
    current_user: User,
) -> SubmissionResult:
    """Grade `answers` against the assigned exam and persist the result.

    Raises `AssignmentNotFoundError` (404), `NotAssignmentOwnerError` (403),
    `InvalidAnswerError` (400) or `AlreadySubmittedError` (409); the router
    maps all four.
    """
    assignment = await session.get(ExamAssignment, assignment_id)
    if assignment is None:
        raise AssignmentNotFoundError(assignment_id)
    # Ownership: a user may only submit against their *own* assignment.
    if assignment.user_id != current_user.id:
        raise NotAssignmentOwnerError(assignment_id)

    exam_id = assignment.exam_id

    # One query for every (question, option) pair in this exam. LEFT JOIN so
    # a question with no options at all still yields a row (with NULLs)
    # instead of silently dropping out of the exam. Ordering by
    # `(order, question_id)` keeps each question's rows contiguous and in
    # exam order, which is what makes the dicts below come out in that order.
    rows = (
        await session.execute(
            select(ExamQuestion.question_id, Option.id, Option.is_correct)
            .select_from(ExamQuestion)
            .outerjoin(Option, Option.question_id == ExamQuestion.question_id)
            .where(ExamQuestion.exam_id == exam_id)
            .order_by(ExamQuestion.order, ExamQuestion.question_id, Option.id)
        )
    ).all()

    correct_option_by_question: dict[int, int | None] = {}
    options_by_question: dict[int, set[int]] = {}
    for question_id, option_id, is_correct in rows:
        correct_option_by_question.setdefault(question_id, None)
        options_by_question.setdefault(question_id, set())
        if option_id is None:  # LEFT JOIN placeholder: question has no options
            continue
        options_by_question[question_id].add(option_id)
        if is_correct and correct_option_by_question[question_id] is None:
            # First correct option wins, should a question ever have >1.
            correct_option_by_question[question_id] = option_id

    # `answer.selected_option_id` is an FK to `option.id`, so a bogus value
    # would blow up as an `IntegrityError` *inside* the transaction below and
    # be misreported as "already submitted". Reject it up front instead, with
    # the data already in hand. Answers for questions outside this exam are
    # skipped here because `grade` discards them anyway.
    for answer in answers:
        if (
            answer.selected_option_id is not None
            and answer.question_id in options_by_question
            and answer.selected_option_id
            not in options_by_question[answer.question_id]
        ):
            raise InvalidAnswerError(
                f"Option {answer.selected_option_id} does not belong to "
                f"question {answer.question_id}"
            )

    graded = grade(correct_option_by_question, answers)
    score = sum(1 for g in graded if g.is_correct)

    # Everything above was reads, which SQLAlchemy served inside an
    # implicitly-begun transaction (`get_current_user` already opened one).
    # `session.begin()` raises if a transaction is active, so end that
    # read-only one here — nothing has been written yet, so this discards
    # nothing. After this point `assignment` is expired and must not be
    # touched; `exam_id` was copied out above for exactly that reason.
    await session.rollback()

    submission = Submission(exam_assignment_id=assignment_id, score=score)
    try:
        # CRIT-1: the Submission insert and every Answer insert live in ONE
        # transaction. Leaving the block commits; any exception raised
        # inside it rolls the whole thing back, leaving no orphan Submission.
        async with session.begin():
            session.add(submission)
            await session.flush()  # assigns submission.id for the FKs below
            for g in graded:
                session.add(
                    Answer(
                        submission_id=submission.id,
                        question_id=g.question_id,
                        selected_option_id=g.selected_option_id,
                        is_correct=g.is_correct,
                    )
                )
    except IntegrityError:
        # WARN-2: unique violation on `exam_assignment_id` — the exam was
        # already submitted. `session.begin()` has already rolled back; this
        # is a belt-and-braces no-op that guarantees a clean session.
        await session.rollback()
        raise AlreadySubmittedError(assignment_id)

    return SubmissionResult(
        submission_id=submission.id,
        score=score,
        total_questions=len(graded),
        breakdown=graded,
    )
