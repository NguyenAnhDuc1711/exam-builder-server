# Handoff: T012 — Exam assembly + assignment

## What Was Done

- **`app/application/use_cases/assemble_exam.py`**: `create_exam(session,
  title, question_ids: list[int]) -> Exam`. Validates ALL `question_ids`
  exist with one query — `select(Question.id).where(Question.id.in_(question_ids))`
  — then does `set(question_ids) - existing_ids`; if non-empty, raises
  `MissingQuestionsError(missing_ids: list[int])` **before** any `Exam`/
  `ExamQuestion` object is created or `session.add`ed (WARN-1: no partial
  insert possible because nothing is added until validation passes).
  `ExamQuestion.order` is set from `enumerate(question_ids)` — 0-based,
  matching the input list's order exactly.
- **`app/application/use_cases/assign_exam.py`**: `assign_exam(session,
  exam_id, user_id) -> ExamAssignment`. Checks `Exam` exists (`session.get`,
  else `ExamNotFoundError`), then `User` exists **and** `role == "user"`
  (else `UserNotFoundError` — same exception for "not found" and "wrong
  role", both map to 404 per 012.md). Does NOT pre-check duplicate
  assignment with a SELECT — relies on T002's DB-level
  `UniqueConstraint("exam_id", "user_id")` on `exam_assignment`; a duplicate
  surfaces as `IntegrityError` from `commit()`, caught here, session is
  rolled back, and `DuplicateAssignmentError` is raised (409). Same
  check-then-insert-is-not-atomic trade-off T010's `create_user` documents
  for email uniqueness.
- **`app/api/v1/routers/exams.py`**: router-level
  `dependencies=[Depends(require_role("admin"))]` (same DRY pattern T011
  used for `/questions`, covers all three routes in one place).
  - `POST /exams` — body `{title: str, question_ids: list[int]}` → 201
    `ExamResponse{id, title, exam_questions: [{question_id, order}]}`, or
    404 `{"detail": {"message": ..., "missing_ids": [...]}}` on WARN-1.
  - `POST /exams/{exam_id}/assign` — body `{user_id: int}` → 201
    `ExamAssignmentResponse{id, exam_id, user_id}`; 404 if exam or user
    missing/wrong-role; 409 on duplicate.
  - `GET /exams/{exam_id}` — 200 `ExamResponse` (same shape as create) or
    404. Uses `selectinload(Exam.exam_questions)` — `Exam.exam_questions`
    relationship has `order_by="ExamQuestion.order"` (set in T002's model),
    so both create and get responses come back in the correct order
    without any extra sorting in the router.
- **`app/main.py`**: added `exams` to the router import and
  `app.include_router(exams.router)` — same integration-wiring pattern
  T003/T010/T011 used; without it `/exams` doesn't exist in the running
  app.
- **Tests** (unexecuted): `tests/integration/test_exam_assembly.py`
  (valid ids in a deliberately non-id-sorted order → 201 + order preserved
  in both the response and a direct DB query; one missing id among valid
  ones → 404 with `missing_ids` containing it, then asserts `SELECT * FROM
  exam` and `SELECT * FROM exam_question` are both empty — proves no
  partial insert) and `tests/integration/test_exam_assignment.py`
  (successful assign → 201, duplicate assign → 409, assign to a
  `user_id` that doesn't exist → 404). All follow the
  ASGI-through-httpx + `get_session` override pattern from
  `tests/integration/test_admin_users.py`. Questions/exams are inserted
  directly via the `session` fixture rather than through `POST /questions`
  — assembly only needs `Question.id` to exist, not real option content.

## Decisions Made

- **`ExamQuestion.order` is 0-based**, taken directly from the input
  list's position (`enumerate(question_ids)`, no `start=1`). Not specified
  by 012.md either way; picked as the simplest option. `Exam.exam_questions`
  is always returned/loaded sorted by this column (T002's `order_by=` on
  the relationship), so absolute value never matters — only relative order.
- **`UserNotFoundError` is shared between "user_id doesn't exist" and
  "user exists but role != 'user'"** — 012.md's acceptance criteria only
  specifies 404 for a missing `user_id` and doesn't give a separate test
  for "exists but is an admin", but the Implementation Steps explicitly
  say to validate role too. Collapsing both into one exception/one 404 is
  the simplest interpretation; flagged here in case a stricter distinction
  (e.g. a different 400/422 for "wrong role but exists") is wanted later.
- **No pre-check SELECT for duplicate assignment** — deliberately relies
  on the unique constraint + `IntegrityError` catch instead of
  `SELECT ... WHERE exam_id=... AND user_id=...` first, to avoid a
  check-then-insert race (same reasoning as `create_user`/email). Means a
  duplicate assignment attempt always costs one failed `INSERT` +
  `rollback()`.
- **Empty `question_ids` list is not rejected** — `create_exam([])` would
  succeed and create an exam with zero questions. 012.md's acceptance
  criteria don't mention this case; left unenforced per "surgical
  changes." Flag for T020 or a future task if an exam must have ≥1
  question before it can be assigned/taken.

## Files Changed

Created:
- `app/application/use_cases/assemble_exam.py`
- `app/application/use_cases/assign_exam.py`
- `app/api/v1/routers/exams.py`
- `tests/integration/test_exam_assembly.py`
- `tests/integration/test_exam_assignment.py`

Modified:
- `app/main.py` (router wiring only — added `exams` import + `include_router`)
- `.sdd/epics/exam-builder-base/012.md` (frontmatter: status closed)

## Warnings for Next Task

- **Nothing was executed.** Still no Python/Docker in this environment
  across T001–T012. Run the full suite (needs a live Postgres per
  `tests/conftest.py`) and fix failures in place before trusting any of
  this — especially the `IntegrityError` catch-and-rollback path in
  `assign_exam` (never run against a real Postgres unique-violation) and
  the `selectinload` + `order_by` interaction on `Exam.exam_questions`
  (never verified the relationship actually comes back sorted at
  runtime).

- **`ExamAssignment` model fields (for T020, submission+grading+results)**
  — `app.infrastructure.db.models.exam.ExamAssignment`: `id: int` (PK,
  this is the "exam_assignment_id" T020 needs to key a `Submission` off
  of — see `submission.exam_assignment_id`, `UniqueConstraint` there
  enforces FR-6's single-attempt rule), `exam_id: int` (FK → `exam.id`),
  `user_id: int` (FK → `user.id`), `assigned_at: datetime`
  (server-default `now()`). Relationships: `.exam` → `Exam`, `.user` →
  `User` (both plain `relationship()`, no `back_populates`, so they are
  lazy-load-only — `session.get(ExamAssignment, id)` then
  `await session.get(Exam, assignment.exam_id)` or use
  `selectinload(ExamAssignment.exam)` explicitly if T020 needs eager
  loading in an async context, same caveat T011's handoff notes for
  `Question.options`).
  To get from an `assignment_id` to the exam's questions in order:
  `assignment = await session.get(ExamAssignment, assignment_id)` →
  `exam = await session.execute(select(Exam).where(Exam.id ==
  assignment.exam_id).options(selectinload(Exam.exam_questions)))` →
  `exam.exam_questions` is already sorted by `.order` (relationship-level
  `order_by`, see `app/infrastructure/db/models/exam.py`).
- **How questions are ordered / how to grade (for T020)**: `ExamQuestion`
  has composite PK `(exam_id, question_id)` plus an `order: int` column.
  `Answer` (in `app/infrastructure/db/models/submission.py`) references
  `question_id` directly (FK to `question.id`), **not** a position/order
  value — so grading should match each submitted answer to the correct
  `Option.is_correct` **by `question_id`**, not by sequence position.
  `ExamQuestion.order` only matters for *display* order (e.g. presenting
  the exam to the user in the right sequence); it is irrelevant to
  correctness grading, which is a straightforward `question_id` /
  `selected_option_id` → `Option.is_correct` lookup per `Answer` row.
- **`submission.exam_assignment_id` is UNIQUE`** (already in the schema
  from an earlier task, confirmed here by reading
  `app/infrastructure/db/models/submission.py`) — a second `POST` against
  the same assignment will hit this constraint; T020 should decide
  whether to pre-check with a SELECT (simpler, matches this task's exam
  lookup style) or catch `IntegrityError` like `assign_exam` does (avoids
  a race but adds rollback complexity) for FR-6's single-attempt rule.
- **No `PATCH`/`DELETE /exams`, no `GET /exams` (list-all)** — out of
  scope for 012.md (only `POST /exams`, `POST /exams/{id}/assign`,
  `GET /exams/{id}` were specified). If T020 or a later task needs to
  list all exams or all assignments for a user, that's new work.
