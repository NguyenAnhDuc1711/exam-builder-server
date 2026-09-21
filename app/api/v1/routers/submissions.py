"""`/exams/{id}/submit` + `/submissions` — submission and results (FR-6, FR-7).

Auth differs per route, so there is no router-level gate here (unlike
`questions.py` / `exams.py`):

- `POST /exams/{assignment_id}/submit` — any authenticated user; the use
  case rejects an assignment that is not theirs with 403.
- `GET /submissions/{submission_id}` — any authenticated user; the use case
  enforces "owner or admin" (CRIT-2) before reading any result data.
- `GET /exams/{exam_id}/submissions` — `require_role("admin")`.

`POST /exams/{assignment_id}/submit` takes the **assignment** id, not the
exam id (an `ExamAssignment` is what pins the exam to this user), and does
not collide with `exams.py`'s `POST /exams/{exam_id}/assign` or
`GET /exams/{exam_id}`.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, require_role
from app.application.use_cases.get_results import (
    NotSubmissionOwnerError,
    SubmissionNotFoundError,
    get_submission,
    list_submissions_for_exam,
)
from app.application.use_cases.submit_exam import (
    AlreadySubmittedError,
    AnswerInput,
    AssignmentNotFoundError,
    InvalidAnswerError,
    NotAssignmentOwnerError,
    submit_exam,
)
from app.infrastructure.db.models.user import User
from app.infrastructure.db.session import get_session

router = APIRouter(tags=["submissions"])


class AnswerRequest(BaseModel):
    question_id: int
    # Omit or send null for a question left unanswered.
    selected_option_id: int | None = None


class SubmitExamRequest(BaseModel):
    answers: list[AnswerRequest]


class GradedAnswerResponse(BaseModel):
    question_id: int
    selected_option_id: int | None
    is_correct: bool


class SubmitExamResponse(BaseModel):
    submission_id: int
    # Number of questions answered correctly (0..total_questions).
    score: int
    total_questions: int
    breakdown: list[GradedAnswerResponse]


class SubmissionResponse(BaseModel):
    id: int
    exam_assignment_id: int
    score: int
    total_questions: int
    submitted_at: datetime
    answers: list[GradedAnswerResponse]


class ExamSubmissionResponse(SubmissionResponse):
    # Who submitted it — admins list by exam, so the owner must be explicit.
    user_id: int


@router.post(
    "/exams/{assignment_id}/submit",
    response_model=SubmitExamResponse,
    status_code=status.HTTP_201_CREATED,
)
async def submit_exam_route(
    assignment_id: int,
    body: SubmitExamRequest,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> SubmitExamResponse:
    answers = [
        AnswerInput(
            question_id=a.question_id, selected_option_id=a.selected_option_id
        )
        for a in body.answers
    ]
    try:
        result = await submit_exam(session, assignment_id, answers, current_user)
    except AssignmentNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found"
        )
    except NotAssignmentOwnerError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="This exam is not assigned to you",
        )
    except InvalidAnswerError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        )
    except AlreadySubmittedError:
        # WARN-2: a clean 409, never a bare IntegrityError traceback/500.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Exam already submitted"
        )

    return SubmitExamResponse(
        submission_id=result.submission_id,
        score=result.score,
        total_questions=result.total_questions,
        breakdown=[
            GradedAnswerResponse(
                question_id=g.question_id,
                selected_option_id=g.selected_option_id,
                is_correct=g.is_correct,
            )
            for g in result.breakdown
        ],
    )


@router.get("/submissions/{submission_id}", response_model=SubmissionResponse)
async def get_submission_route(
    submission_id: int,
    session: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> SubmissionResponse:
    try:
        submission = await get_submission(session, submission_id, current_user)
    except SubmissionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found"
        )
    except NotSubmissionOwnerError:
        # CRIT-2: nothing about the submission is in this response.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden"
        )

    return SubmissionResponse(
        id=submission.id,
        exam_assignment_id=submission.exam_assignment_id,
        score=submission.score,
        # One Answer row is written per exam question, so this is the total.
        total_questions=len(submission.answers),
        submitted_at=submission.submitted_at,
        answers=[
            GradedAnswerResponse(
                question_id=a.question_id,
                selected_option_id=a.selected_option_id,
                is_correct=a.is_correct,
            )
            for a in submission.answers
        ],
    )


@router.get(
    "/exams/{exam_id}/submissions",
    response_model=list[ExamSubmissionResponse],
    dependencies=[Depends(require_role("admin"))],
)
async def list_exam_submissions_route(
    exam_id: int,
    session: AsyncSession = Depends(get_session),
) -> list[ExamSubmissionResponse]:
    submissions = await list_submissions_for_exam(session, exam_id)
    # Everything touched below was eager-loaded by the use case (WARN-4) —
    # no lazy load is triggered here, which in async would raise anyway.
    return [
        ExamSubmissionResponse(
            id=s.id,
            exam_assignment_id=s.exam_assignment_id,
            user_id=s.exam_assignment.user_id,
            score=s.score,
            total_questions=len(s.answers),
            submitted_at=s.submitted_at,
            answers=[
                GradedAnswerResponse(
                    question_id=a.question_id,
                    selected_option_id=a.selected_option_id,
                    is_correct=a.is_correct,
                )
                for a in s.answers
            ],
        )
        for s in submissions
    ]
