from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_role
from app.api.rate_limit import rate_limit
from app.schemas.submissions import (
    ExamSubmissionResponse,
    GradedAnswerResponse,
    SubmissionResponse,
    SubmitExamRequest,
    SubmitExamResponse,
)
from app.services.get_results import (
    NotSubmissionOwnerError,
    SubmissionNotFoundError,
    get_submission,
    list_submissions_for_exam,
)
from app.services.submit_exam import (
    AlreadySubmittedError,
    AnswerInput,
    AssignmentNotFoundError,
    InvalidAnswerError,
    NotAssignmentOwnerError,
    submit_exam,
)
from app.models.user import User
from app.core.database import get_session

router = APIRouter(tags=["submissions"])


@router.post(
    "/exams/{assignment_id}/submit",
    response_model=SubmitExamResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("submit"))],
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


@router.get(
    "/submissions/{submission_id}",
    response_model=SubmissionResponse,
    dependencies=[Depends(rate_limit("read"))],
)
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
    dependencies=[Depends(require_role("admin")), Depends(rate_limit("read"))],
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
