from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.ports.image_storage import ImageStoragePort, UploadError
from app.models.question import Option, Question
from app.crud.question_repository import (
    QuestionRepository,
)

MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024  # 5MB

# Magic-byte signatures for the only image types we accept. Checked against
# the actual file content, not the client-supplied `Content-Type` header.
_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_JPEG_SIGNATURE = b"\xff\xd8\xff"


class InvalidOptionsError(Exception):
    """Options do not contain exactly one `is_correct=True` entry."""


class InvalidImageError(Exception):
    """The attached image failed MIME-type or size validation."""


@dataclass
class OptionInput:
    text: str
    is_correct: bool


@dataclass
class CreateQuestionResult:
    question: Question
    image_upload_warning: str | None


def _has_single_correct_option(options: list[OptionInput]) -> bool:
    return sum(1 for o in options if o.is_correct) == 1


def _sniff_image_content_type(file: bytes) -> str | None:
    """Return the real MIME type of `file` based on its magic bytes, or
    `None` if it is not one of png/jpeg/webp.
    """
    if file.startswith(_PNG_SIGNATURE):
        return "image/png"
    if file.startswith(_JPEG_SIGNATURE):
        return "image/jpeg"
    if len(file) >= 12 and file[0:4] == b"RIFF" and file[8:12] == b"WEBP":
        return "image/webp"
    return None


async def create_question(
    session: AsyncSession,
    image_storage: ImageStoragePort,
    text: str,
    options: list[OptionInput],
    image: bytes | None = None,
) -> CreateQuestionResult:
    if not _has_single_correct_option(options):
        raise InvalidOptionsError("Exactly one option must be marked correct")

    image_url: str | None = None
    image_upload_warning: str | None = None

    if image is not None:
        if len(image) > MAX_IMAGE_SIZE_BYTES:
            raise InvalidImageError("Image exceeds the 5MB size limit")

        content_type = _sniff_image_content_type(image)
        if content_type is None:
            raise InvalidImageError(
                "Unsupported image type; only PNG, JPEG, and WEBP are allowed"
            )

        try:
            image_url = await image_storage.upload(image, content_type)
        except UploadError:
            # NFR-2: a broken image host must not block question creation.
            image_upload_warning = (
                "Image upload failed; question saved without an image"
            )

    question = Question(text=text, image_url=image_url)
    question.options = [
        Option(text=o.text, is_correct=o.is_correct) for o in options
    ]
    QuestionRepository(session).add(question)
    await session.commit()

    return CreateQuestionResult(
        question=question, image_upload_warning=image_upload_warning
    )


async def list_questions(session: AsyncSession) -> list[Question]:
    """Every question in the bank, with its options eager-loaded."""
    return await QuestionRepository(session).list_all_with_options()
