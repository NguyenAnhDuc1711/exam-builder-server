"""Use case: admin creates a question for the question bank (FR-3).

Two rules enforced here, both from plan-review and both checked *before*
any image ever reaches Cloudinary:

- Exactly one option must have `is_correct=True` (else `InvalidOptionsError`,
  mapped to 400 by the router) — `Question.has_single_answer` (domain
  entity) owns the rule, this use case just applies it.
- An attached image's real type is sniffed from its magic bytes (WARN-3) —
  the client-supplied `Content-Type` header is never trusted for this
  check — and its size is capped at 5MB, before `ImageStoragePort.upload`
  is ever called. Either failure raises `InvalidImageError` (400) with
  Cloudinary never invoked.

If the image passes validation but the upload itself fails (network error,
Cloudinary outage, etc.), that is NOT a 400: `UploadError` is caught here
and the question is still saved, with `image_url=None` and a warning
message returned alongside it (NFR-2) — a broken image host must never
block question creation.
"""

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.application.ports.image_storage import ImageStoragePort, UploadError
from app.domain.entities.question import Option as OptionEntity
from app.domain.entities.question import Question as QuestionEntity
from app.infrastructure.db.models.question import Option, Question

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
    """Create and persist a question with its options.

    Raises `InvalidOptionsError` or `InvalidImageError` (both mapped to 400
    by the router) before touching the database or `image_storage`.
    """
    entity_options = [
        OptionEntity(id=None, text=o.text, is_correct=o.is_correct) for o in options
    ]
    if not QuestionEntity(id=None, text=text, options=entity_options).has_single_answer():
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
    session.add(question)
    await session.commit()

    return CreateQuestionResult(
        question=question, image_upload_warning=image_upload_warning
    )
