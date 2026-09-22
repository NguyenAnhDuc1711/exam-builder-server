from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.submission import Answer, Submission
from app.models.user import User
from app.crud.exam_assignment_repository import (
    ExamAssignmentRepository,
)
from app.crud.exam_repository import ExamRepository
from app.crud.submission_repository import (
    SubmissionRepository,
)


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
    assignment = await ExamAssignmentRepository(session).get_by_id(assignment_id)
    if assignment is None:
        raise AssignmentNotFoundError(assignment_id)
    # Ownership: a user may only submit against their *own* assignment.
    if assignment.user_id != current_user.id:
        raise NotAssignmentOwnerError(assignment_id)

    exam_id = assignment.exam_id

    rows = await ExamRepository(session).get_grading_data(exam_id)

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

    await session.rollback()

    submission_repo = SubmissionRepository(session)
    submission = Submission(exam_assignment_id=assignment_id, score=score)
    try:
        async with session.begin():
            submission_repo.add_submission(submission)
            await session.flush()  # assigns submission.id for the FKs below
            for g in graded:
                submission_repo.add_answer(
                    Answer(
                        submission_id=submission.id,
                        question_id=g.question_id,
                        selected_option_id=g.selected_option_id,
                        is_correct=g.is_correct,
                    )
                )
    except IntegrityError:
        await session.rollback()
        raise AlreadySubmittedError(assignment_id)

    return SubmissionResult(
        submission_id=submission.id,
        score=score,
        total_questions=len(graded),
        breakdown=graded,
    )
