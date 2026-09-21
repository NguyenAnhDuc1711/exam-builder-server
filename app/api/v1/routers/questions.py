"""`/questions` — admin-only question bank CRUD (FR-3).

`POST /questions` is `multipart/form-data`, not JSON: the optional `image`
is a file upload alongside `text` and `options`, so `options` travels as a
JSON-encoded string form field and is parsed here before being handed to
the use case.
"""

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel, TypeAdapter, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.dependencies import require_role
from app.application.ports.image_storage import ImageStoragePort
from app.application.use_cases.create_question import (
    InvalidImageError,
    InvalidOptionsError,
    OptionInput,
    create_question,
)
from app.infrastructure.db.models.question import Question
from app.infrastructure.db.session import get_session
from app.infrastructure.storage.cloudinary_service import CloudinaryImageStorage

router = APIRouter(
    prefix="/questions",
    tags=["questions"],
    dependencies=[Depends(require_role("admin"))],
)

# A single long-lived instance: `CloudinaryImageStorage` holds no per-request
# state (the SDK is configured once, at import time).
_image_storage = CloudinaryImageStorage()


def get_image_storage() -> ImageStoragePort:
    return _image_storage


class OptionSchema(BaseModel):
    text: str
    is_correct: bool


_options_adapter = TypeAdapter(list[OptionSchema])


class OptionResponse(BaseModel):
    id: int
    text: str
    is_correct: bool

    model_config = {"from_attributes": True}


class QuestionResponse(BaseModel):
    id: int
    text: str
    image_url: str | None
    options: list[OptionResponse]

    model_config = {"from_attributes": True}


class CreateQuestionResponse(QuestionResponse):
    # Set only when an attached image failed to upload (NFR-2) — the
    # question is still created successfully (201) without it.
    image_upload_warning: str | None = None


@router.post(
    "", response_model=CreateQuestionResponse, status_code=status.HTTP_201_CREATED
)
async def create_question_route(
    text: str = Form(...),
    options: str = Form(...),
    image: UploadFile | None = File(None),
    session: AsyncSession = Depends(get_session),
    image_storage: ImageStoragePort = Depends(get_image_storage),
) -> CreateQuestionResponse:
    try:
        parsed_options = _options_adapter.validate_json(options)
    except ValidationError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid options payload"
        )

    option_inputs = [
        OptionInput(text=o.text, is_correct=o.is_correct) for o in parsed_options
    ]
    image_bytes = await image.read() if image is not None else None

    try:
        result = await create_question(
            session, image_storage, text, option_inputs, image_bytes
        )
    except InvalidOptionsError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        )
    except InvalidImageError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        )

    return CreateQuestionResponse(
        id=result.question.id,
        text=result.question.text,
        image_url=result.question.image_url,
        options=[OptionResponse.model_validate(o) for o in result.question.options],
        image_upload_warning=result.image_upload_warning,
    )


@router.get("", response_model=list[QuestionResponse])
async def list_questions_route(
    session: AsyncSession = Depends(get_session),
) -> list[Question]:
    result = await session.execute(
        select(Question).options(selectinload(Question.options))
    )
    return list(result.scalars().unique().all())
