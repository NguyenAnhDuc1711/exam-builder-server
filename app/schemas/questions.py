"""Request/response models for `/questions`."""

from pydantic import BaseModel, Field, field_validator

from app.core.sanitize import sanitize_text


class OptionSchema(BaseModel):
    text: str = Field(max_length=1000)
    is_correct: bool

    _sanitize_text = field_validator("text")(sanitize_text)


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
    image_upload_warning: str | None = None
