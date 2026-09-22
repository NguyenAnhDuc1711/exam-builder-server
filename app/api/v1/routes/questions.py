"""`/questions` — admin-only question bank CRUD (FR-3).

Every route requires `role="admin"` — a router-level gate applied where
this router is mounted (`app/api/v1/routers/__init__.py`).

`POST /questions` is `multipart/form-data`, not JSON: the optional `image`
is a file upload alongside `text` and `options`, so `options` travels as a
JSON-encoded string form field and is parsed here before being handed to
the use case.
"""

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import TypeAdapter, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.questions import (
    CreateQuestionResponse,
    OptionResponse,
    OptionSchema,
    QuestionResponse,
)
from app.ports.image_storage import ImageStoragePort
from app.services.create_question import (
    InvalidImageError,
    InvalidOptionsError,
    OptionInput,
    create_question,
    list_questions,
)
from app.models.question import Question
from app.core.database import get_session
from app.storage.cloudinary_service import CloudinaryImageStorage

router = APIRouter()

# A single long-lived instance: `CloudinaryImageStorage` holds no per-request
# state (the SDK is configured once, at import time).
_image_storage = CloudinaryImageStorage()


def get_image_storage() -> ImageStoragePort:
    return _image_storage


_options_adapter = TypeAdapter(list[OptionSchema])


@router.post(
    "", response_model=CreateQuestionResponse, status_code=status.HTTP_201_CREATED
)
async def create_question_route(
    # `question.text` is `Text` (unbounded) at the DB layer, so this bound
    # only guards the API boundary (same rationale as `OptionSchema.text`).
    text: str = Form(..., max_length=5000),
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
    return await list_questions(session)
