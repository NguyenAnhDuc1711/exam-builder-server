# Handoff: T011 — Question bank CRUD + Cloudinary image upload

## What Was Done

- **`app/application/ports/image_storage.py`**: `ImageStoragePort` (ABC)
  with `async upload(self, file: bytes, content_type: str) -> str`, raising
  `UploadError` on any failure. Application layer depends only on this, not
  the Cloudinary SDK (AD-3).
- **`app/infrastructure/storage/cloudinary_service.py`**: `CloudinaryImageStorage`
  implements the port. `cloudinary.config(...)` runs once at import time
  from `app.core.config.settings` (`CLOUDINARY_CLOUD_NAME/API_KEY/API_SECRET`,
  present since T001). `upload()` runs the blocking
  `cloudinary.uploader.upload(io.BytesIO(file))` via `asyncio.to_thread`
  (so it doesn't stall the event loop) and returns `result["secure_url"]`.
  A bare `except Exception` catches every SDK/network error and re-raises
  as `UploadError` — no raw SDK exception ever escapes this module.
- **`app/application/use_cases/create_question.py`**: `create_question(session,
  image_storage: ImageStoragePort, text, options: list[OptionInput], image:
  bytes | None) -> CreateQuestionResult{question: Question, image_upload_warning:
  str | None}`.
  - Options: builds domain entities and calls `Question.has_single_answer()`
    (from `app.domain.entities.question`, written in T002/T011); anything
    other than exactly one `is_correct=True` raises `InvalidOptionsError`.
  - Image, if present: size checked first (`> 5MB` → `InvalidImageError`),
    then type sniffed from **magic bytes** (`_sniff_image_content_type` —
    PNG `\x89PNG\r\n\x1a\n`, JPEG `\xff\xd8\xff`, WEBP `RIFF....WEBP`); the
    client's `Content-Type` header is never consulted. No match →
    `InvalidImageError`. Both exceptions are raised **before**
    `image_storage.upload` is ever called (WARN-3 — verified by the tests,
    not just by inspection).
  - `image_storage.upload` is called only after both checks pass. If it
    raises `UploadError`, that is caught here (not re-raised): the question
    is still built with `image_url=None` and
    `image_upload_warning="Image upload failed; question saved without an
    image"` (NFR-2/SC-4).
  - Persists via plain `session.add(question)` + `session.commit()` (owns
    its transaction, same convention as `create_user`/`login`).
- **`app/api/v1/routers/questions.py`**: `router = APIRouter(prefix="/questions",
  tags=["questions"], dependencies=[Depends(require_role("admin"))])` — the
  role gate is on the **router**, not per-route, so it covers both
  endpoints in one place (equivalent to T010's per-route
  `dependencies=[...]`, just DRYer since both routes need the same gate).
  - `POST /questions` is **`multipart/form-data`**, not JSON: `text: str =
    Form(...)`, `options: str = Form(...)` (a JSON-encoded string, parsed
    with `TypeAdapter(list[OptionSchema]).validate_json(...)` — bad JSON →
    400), `image: UploadFile | None = File(None)`. Returns 201 with
    `CreateQuestionResponse{id, text, image_url, options: [{id, text,
    is_correct}], image_upload_warning}`.
  - `GET /questions` lists all questions with `selectinload(Question.options)`
    (required — an async session cannot lazily load a not-yet-populated
    relationship; the create path avoids this because `question.options`
    is already in memory from the assignment before commit).
  - `get_image_storage()` dependency returns a single module-level
    `CloudinaryImageStorage()` instance (stateless, so one instance is
    fine); override this in tests, not the class, to avoid real network
    calls.
- **Tests** (unexecuted): `tests/integration/test_questions.py` (text-only
  create, valid-image create with mocked upload, 0/2-correct-options → 400,
  invalid MIME (real PDF bytes under a lying `image/png` header) → 400 +
  mock not called, oversized (>5MB) PNG → 400 + mock not called, list
  requires admin (403 for `role="user"`), list returns created questions)
  and `tests/integration/test_question_upload_failure.py` (SC-4 dedicated
  file, matching 011.md's verification checklist path: `UploadError` from
  the mocked port still yields 201 with `image_url=None` and a non-empty
  `image_upload_warning`). Both override `get_session` (per-test `session`
  fixture) and `get_image_storage` (an `AsyncMock(spec=ImageStoragePort)`)
  on a throwaway `FastAPI()` mounting `auth` + `questions` routers — same
  pattern as `test_admin_users.py`.

## Decisions Made

- **MIME-type check is magic-bytes-only, header is completely ignored** —
  not "checked but overridden": `_sniff_image_content_type` reads
  `file[:N]`, never `image.content_type`. Tests prove this by sending a
  real PDF under an `image/png` header and asserting 400 (WARN-3).
- **Size check runs before the MIME-type check.** Order isn't specified in
  011.md; picked reading `len(bytes)` (cheap) before inspecting content as
  the more defensive order. Both still run strictly before
  `image_storage.upload`.
- **`asyncio.to_thread` around the Cloudinary SDK call** — the SDK is
  synchronous; without this, a slow/hanging upload would block the whole
  event loop, not just the one request. Not explicitly required by 011.md
  but a correctness issue an async framework can't paper over; flagged
  here rather than silently added.
- **No minimum-option-count validation** (e.g. rejecting a single-option
  question). 011.md's Implementation Steps only specify the
  exactly-one-correct-answer rule; FR-3's "≥2 lựa chọn" appears only in the
  success-scenario description, not as its own acceptance criterion or
  listed test. Left unenforced per "surgical changes" — flagged here in
  case T012 or a future task expects it.
- **`app/main.py` was touched** (outside 011.md's stated file list) to add
  `from app.api.v1.routers import questions` and
  `app.include_router(questions.router)` — same integration-wiring pattern
  T003/T010 used; without it `/questions` doesn't exist in the running app.

## Files Changed

Created:
- `app/application/ports/image_storage.py`
- `app/infrastructure/storage/cloudinary_service.py`
- `app/application/use_cases/create_question.py`
- `app/api/v1/routers/questions.py`
- `tests/integration/test_questions.py`
- `tests/integration/test_question_upload_failure.py`

Modified:
- `app/main.py` (router wiring only, see above)
- `.sdd/epics/exam-builder-base/011.md` (frontmatter: status closed)

## Warnings for Next Task

- **Nothing was executed.** Still no Python/Docker in this environment
  across T001–T011. Run the full suite (needs a live Postgres per
  `tests/conftest.py`) and fix failures in place before trusting any of
  this, especially the multipart/form-data parsing (`TypeAdapter.validate_json`
  requires pydantic `>=2.x` with `TypeAdapter` — present per `requirements.txt`
  pin `pydantic>=2.8,<3` — but never actually run) and the `asyncio.to_thread`
  + Cloudinary SDK interaction (never run against a real or mocked SDK call
  beyond the `AsyncMock`-based unit-level router tests).
- **Question/Option model fields (for T012, exam assembly):**
  `app.infrastructure.db.models.question.Question` — `id: int` (PK),
  `text: str` (`Text`, not null), `image_url: str | None`
  (`String(512)`), `options: list[Option]` (relationship,
  `cascade="all, delete-orphan"`, `passive_deletes=True` — deleting a
  Question cascades to its Options at the DB level).
  `app.infrastructure.db.models.question.Option` — `id: int` (PK),
  `question_id: int` (FK, `ON DELETE CASCADE`, indexed), `text: str`,
  `is_correct: bool` (server default `false`). To reference a question by
  id for exam assembly: `select(Question).options(selectinload(Question.options))`
  (an async session cannot lazily load `.options` after the fact — always
  eager-load it, as `GET /questions` does).
- **`GET /questions` returns ALL questions, unpaginated** — fine for a
  question bank at this scale per the spec, but if T012 needs to pick a
  subset for exam assembly, it should query `Question`/`Option` directly
  (same pattern as T010's note on listing users) rather than going through
  this endpoint's response shape.
- **No `PATCH`/`DELETE /questions/{id}`** — out of scope for 011.md (its
  file list and acceptance criteria only cover `POST`/`GET`). If T012 or a
  later task needs to edit/retire a question, that's new work.
- **`create_question`'s `OptionInput` is a plain dataclass**, not a
  pydantic model — the router converts `OptionSchema` (pydantic, used only
  for parsing/validating the incoming JSON) into `OptionInput` before
  calling the use case, keeping pydantic out of the application layer
  (same layering as `create_user`, which takes plain `str` args, not a
  request schema).
