from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.deps import require_role
from app.api.rate_limit import rate_limit
from app.schemas.exams import (
    AssignExamRequest,
    CreateExamRequest,
    ExamAssignmentResponse,
    ExamResponse,
)
from app.services.assemble_exam import (
    MissingQuestionsError,
    create_exam,
    get_exam,
)
from app.services.assign_exam import (
    DuplicateAssignmentError,
    ExamNotFoundError,
    UserNotFoundError,
    assign_exam,
)
from app.models.exam import Exam, ExamAssignment
from app.core.database import get_session

router = APIRouter(
    prefix="/exams",
    tags=["exams"],
    dependencies=[Depends(require_role("admin"))],
)


@router.post(
    "",
    response_model=ExamResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("write"))],
)
async def create_exam_route(
    body: CreateExamRequest,
    session: AsyncSession = Depends(get_session),
) -> Exam:
    try:
        return await create_exam(session, body.title, body.question_ids)
    except MissingQuestionsError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "message": "Unknown question ids",
                "missing_ids": exc.missing_ids,
            },
        )


@router.post(
    "/{exam_id}/assign",
    response_model=ExamAssignmentResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("write"))],
)
async def assign_exam_route(
    exam_id: int,
    body: AssignExamRequest,
    session: AsyncSession = Depends(get_session),
) -> ExamAssignment:
    try:
        return await assign_exam(session, exam_id, body.user_id)
    except (ExamNotFoundError, UserNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Not found"
        )
    except DuplicateAssignmentError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Exam already assigned to this user",
        )


@router.get(
    "/{exam_id}",
    response_model=ExamResponse,
    dependencies=[Depends(rate_limit("read"))],
)
async def get_exam_route(
    exam_id: int,
    session: AsyncSession = Depends(get_session),
) -> Exam:
    exam = await get_exam(session, exam_id)
    if exam is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Exam not found"
        )
    return exam
