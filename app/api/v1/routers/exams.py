"""`/exams` — admin-only exam assembly + assignment (FR-4, FR-5).

Both routes and `GET /exams/{id}` require `role="admin"` (router-level
gate, same pattern as `app/api/v1/routers/questions.py`).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import require_role
from app.application.use_cases.assemble_exam import (
    MissingQuestionsError,
    create_exam,
)
from app.application.use_cases.assign_exam import (
    DuplicateAssignmentError,
    ExamNotFoundError,
    UserNotFoundError,
    assign_exam,
)
from app.infrastructure.db.models.exam import Exam, ExamAssignment
from app.infrastructure.db.session import get_session

router = APIRouter(
    prefix="/exams",
    tags=["exams"],
    dependencies=[Depends(require_role("admin"))],
)


class CreateExamRequest(BaseModel):
    title: str
    question_ids: list[int]


class ExamQuestionResponse(BaseModel):
    question_id: int
    order: int

    model_config = {"from_attributes": True}


class ExamResponse(BaseModel):
    id: int
    title: str
    exam_questions: list[ExamQuestionResponse]

    model_config = {"from_attributes": True}


class AssignExamRequest(BaseModel):
    user_id: int


class ExamAssignmentResponse(BaseModel):
    id: int
    exam_id: int
    user_id: int

    model_config = {"from_attributes": True}


@router.post("", response_model=ExamResponse, status_code=status.HTTP_201_CREATED)
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


@router.get("/{exam_id}", response_model=ExamResponse)
async def get_exam_route(
    exam_id: int,
    session: AsyncSession = Depends(get_session),
) -> Exam:
    exam = (
        await session.execute(
            select(Exam)
            .where(Exam.id == exam_id)
            .options(selectinload(Exam.exam_questions))
        )
    ).scalar_one_or_none()
    if exam is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Exam not found"
        )
    return exam
