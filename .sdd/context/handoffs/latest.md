# Handoff: T020 — Submission + auto-grading + results (last task before T090)

T020 is the final business-logic task of `exam-builder-base`. This handoff
therefore covers **T020 in detail plus a whole-epic picture** for T090
(verification).

---

## Part 1 — What T020 built

### `app/application/use_cases/submit_exam.py`

- `grade(correct_option_by_question: dict[int, int | None], answers) ->
  list[GradedAnswer]` — **pure, no I/O**, so `tests/unit/test_grading.py`
  is a real unit test (SC-2). The dict maps every `question_id` *in the
  exam* to its correct `Option.id` (or `None`); **its insertion order is
  the exam order**, and the breakdown follows it.
  - The **exam**, not the payload, decides which questions are graded:
    skipped/omitted questions become `selected_option_id=None,
    is_correct=False`; answers for `question_id`s outside the exam are
    ignored (they cannot inflate the score); a repeated `question_id`
    resolves to its last occurrence.
  - Matching is **by `question_id`**, never by list position (per T012's
    handoff — `ExamQuestion.order` is display-only).
- `submit_exam(session, assignment_id, answers, current_user) ->
  SubmissionResult`:
  1. `session.get(ExamAssignment, ...)` → `AssignmentNotFoundError` (404).
  2. `assignment.user_id != current_user.id` → `NotAssignmentOwnerError`
     (403).
  3. One SELECT for every `(question, option)` pair of the exam
     (`ExamQuestion LEFT OUTER JOIN Option`, ordered by
     `order, question_id, option.id`) → builds both the answer key and the
     set of legal option ids per question.
  4. **`InvalidAnswerError` (400)** if a `selected_option_id` is not an
     option of its question — see "Deviations" below.
  5. `grade(...)`, `score = number of correct answers`.
  6. **CRIT-1**, see Part 2.
  7. **WARN-2**: `except IntegrityError` → `AlreadySubmittedError` (409).

### `app/application/use_cases/get_results.py`

- `get_submission(session, submission_id, current_user)` — **CRIT-2**, see
  Part 2. Returns the `Submission` with `answers` eager-loaded.
- `list_submissions_for_exam(session, exam_id)` — admin-only (enforced at
  the router). **WARN-4**: `joinedload(Submission.exam_assignment)` +
  `selectinload(Submission.answers)` ⇒ a constant 2 statements regardless
  of how many submissions the exam has. Ordered by `Submission.id`.

### `app/api/v1/routers/submissions.py`

No router-level auth gate (auth differs per route, unlike
`questions.py`/`exams.py`):

| Route | Auth | Codes |
|---|---|---|
| `POST /exams/{assignment_id}/submit` | `get_current_user` | 201 / 400 / 403 / 404 / 409 |
| `GET /submissions/{submission_id}` | `get_current_user` | 200 / 403 / 404 |
| `GET /exams/{exam_id}/submissions` | `require_role("admin")` | 200 / 403 |

The path takes the **assignment id**, not the exam id. It does not collide
with `exams.py`'s `POST /exams/{exam_id}/assign` or `GET /exams/{exam_id}`
(different literal suffixes), so router registration order is irrelevant.

Response shapes:
- submit → `{submission_id, score, total_questions, breakdown[{question_id,
  selected_option_id, is_correct}]}`
- get → `{id, exam_assignment_id, score, total_questions, submitted_at,
  answers[...]}`
- list → the same plus `user_id`.

### `app/main.py`

Added `submissions` to the router import and
`app.include_router(submissions.router)` — integration wiring only, same
pattern as T003/T010/T011/T012.

---

## Part 2 — How the two CRITICAL findings are closed

### CRIT-1 — one transaction around Submission + Answers

```python
await session.rollback()          # end the implicit READ transaction

submission = Submission(exam_assignment_id=assignment_id, score=score)
try:
    async with session.begin():   # CRIT-1: one transaction
        session.add(submission)
        await session.flush()     # assigns submission.id
        for g in graded:
            session.add(Answer(submission_id=submission.id, ...))
except IntegrityError:
    await session.rollback()
    raise AlreadySubmittedError(assignment_id)
```

- Every write — the `Submission` INSERT and all N `Answer` INSERTs — is
  inside the single `async with session.begin():` block. The block commits
  only on clean exit; **any** exception inside it makes SQLAlchemy roll the
  whole transaction back, so an orphan `Submission` without its `Answer`
  rows is not reachable.
- **`await session.rollback()` before `session.begin()` is load-bearing, do
  not delete it.** `get_current_user` and the reads above already
  autobegan a transaction, and `AsyncSession.begin()` raises
  `InvalidRequestError` if one is active. The rollback ends that read-only
  transaction (discarding nothing — nothing has been written yet) and is a
  documented no-op if no transaction is active, so it is correct either
  way. **Consequence:** `assignment` and `current_user` are expired after
  that line, which is why `exam_id` is copied into a local *before* it.
- The `except IntegrityError` rollback is belt-and-braces: the context
  manager has already rolled back (SQLAlchemy's `SessionTransaction.__exit__`
  rolls back when `commit()` raises), and a second `rollback()` is a
  pass-through.

### CRIT-2 — ownership checked before any data is read

`get_submission` is deliberately **two queries**:

```python
# Step 1: fetch the OWNER ONLY — no score, no answers, nothing leakable.
owner_user_id = (await session.execute(
    select(ExamAssignment.user_id)
      .select_from(Submission)
      .join(ExamAssignment, ExamAssignment.id == Submission.exam_assignment_id)
      .where(Submission.id == submission_id)
)).scalar_one_or_none()

if owner_user_id is None:
    raise SubmissionNotFoundError(submission_id)          # 404
if current_user.role != "admin" and owner_user_id != current_user.id:
    raise NotSubmissionOwnerError(submission_id)          # 403

# Step 2: authorised — only NOW is any result data read.
submission = ... select(Submission).options(selectinload(Submission.answers)) ...
```

The first query selects a single scalar (the owner's user id) and nothing
else, so for an unauthorised caller **no submission data is ever loaded
into memory, let alone returned** — this is stronger than "load then
filter" and makes an ordering mistake structurally impossible. Admins skip
the owner comparison (`role != "admin"` short-circuits), so CRIT-2 cannot
lock admins out. The router renders `NotSubmissionOwnerError` as exactly
`{"detail": "Forbidden"}`.

---

## Part 3 — Tests written by T020 (all unexecuted)

- `tests/unit/test_grading.py` (SC-2) — 8 pure tests against a fixed
  answer key: all-correct, all-wrong, mixed, **shuffled payload (proves
  matching is by `question_id`, not position)**, unanswered/omitted,
  extra-ids-ignored, question with no correct option, empty exam.
- `tests/integration/test_submit_transaction.py` — happy-path grading +
  persistence; 403 for someone else's assignment; 400 for an option from
  another question; **CRIT-1**; **WARN-2** double-submit → 409.
  - **CRIT-1 injection technique (documented in the test docstring):**
    `submit_exam` calls `session.add` exactly once for the `Submission`
    and once per `Answer`. The test `monkeypatch.setattr`s `session.add`
    on the *instance* with a counting wrapper that raises `RuntimeError`
    on the **3rd** call — i.e. after the `Submission` was added *and
    flushed* (its INSERT really reached Postgres, `submission.id`
    allocated) and after `Answer#1`, but before `Answer#2`. The request is
    wrapped in `pytest.raises(RuntimeError)` (Starlette's
    `ServerErrorMiddleware` re-raises). Then a **separate session over
    `db_engine`** asserts `COUNT(submission) == 0` and
    `COUNT(answer) == 0`, and a retry submit returns 201 (proving the
    rollback was complete enough to free the unique constraint).
- `tests/integration/test_results_authz.py` — **the most important file**:
  owner → 200 + breakdown; **user B → 403 with assertions on the raw
  response text** (`"score"`, `"is_correct"`, `"answers"`, `"breakdown"`
  and every question/option id must be absent, and the body must equal
  `{"detail": "Forbidden"}`); unauthenticated → 401; **admin → 200**;
  unknown id → 404.
- `tests/integration/test_results_n_plus_1.py` (WARN-4) — counts real SQL
  with `event.listen(db_engine.sync_engine, "before_cursor_execute", ...)`
  and asserts the statement count for an exam with **6** submissions
  **equals** the count for one with **2** (and is ≤ 3). A warm-up request
  precedes the measurements so identity-map caching cannot skew them. Also
  covers the response shape and that a non-admin gets 403.

---

## Part 4 — Deviations / decisions T090 should know about

1. **`score` is a count, not a ratio.** 020.md §1 says "score = số câu
   đúng / tổng số câu", but `submission.score` is an `Integer` column
   (T002) and changing it needs a migration, which is out of T020's scope.
   Stored value = **number of correct answers**; the API also returns
   `total_questions`, so the ratio is exactly derivable and nothing is
   lost to rounding.
2. **Domain exceptions, not `HTTPException`, in the use cases.** 020.md's
   Anchor Code raises `HTTPException(403)` directly inside the use case;
   every other use case in this repo (`assign_exam`, `create_question`,
   `create_user`) raises a domain error that the router maps. T020 follows
   the repo pattern (CLAUDE.md: "Follow existing patterns"). The HTTP
   semantics are identical.
3. **New, unspecified `InvalidAnswerError` → 400.** `answer.selected_option_id`
   is an FK to `option.id`; a bogus value would have raised `IntegrityError`
   *inside* the CRIT-1 transaction and been mistranslated into WARN-2's
   409 "Exam already submitted" for an exam that was never submitted. The
   validation is done from data already fetched (no extra query). If T090
   considers this out of scope it can be removed, but the 409
   mis-classification would come back.
4. **No pre-check SELECT for "already submitted".** Per 020.md's Technical
   Details, the DB unique constraint is the only source of truth; two
   concurrent requests could both pass such a check. Cost: a duplicate
   submit is always one failed INSERT + rollback.
5. `list_submissions_for_exam` uses both an explicit `.join(ExamAssignment)`
   (for the `exam_id` filter) and `joinedload(Submission.exam_assignment)`
   (for eager loading), so the emitted SQL contains two joins to
   `exam_assignment` — correct, if slightly redundant. `contains_eager`
   would collapse them.

---

## Part 5 — Whole-epic picture for T090

### Shipped, per task (all committed on `epic/exam-builder-base`)

| Task | Commit | Surface |
|---|---|---|
| T001 | `928077d` | Scaffolding, Docker Compose, Alembic init, `pytest.ini`, `requirements.txt` |
| T002 | `65957b3` | Domain entities + SQLAlchemy models + initial migration (all constraints below) |
| T003 | `a3a8517` | `/auth/login`, `/auth/refresh` — JWT access/refresh, rotation, reuse detection |
| T010 | `00c3d3e` | `/users` — admin user management |
| T011 | `fb76287` | `/questions` — question bank + Cloudinary upload (graceful degradation, NFR-2) |
| T012 | `954eeee` | `/exams` — assembly + assignment |
| T020 | this one | `/exams/{id}/submit`, `/submissions/{id}`, `/exams/{id}/submissions` |

### Shared infrastructure T090 will exercise

- `app/api/dependencies.py` — `get_current_user` (401) and
  `require_role(role)` (403, checked against the **DB** row, not the token
  claim). Both resolve `get_session`, which FastAPI caches per request, so
  the whole request shares one `AsyncSession`.
- `app/infrastructure/db/session.py` — `expire_on_commit=False`, and
  `get_session` **never commits on your behalf**; the use case owns the
  transaction boundary.
- DB-level rules that the application relies on rather than re-checking:
  `user.email` UNIQUE, `exam_assignment (exam_id, user_id)` UNIQUE,
  `exam_question` composite PK `(exam_id, question_id)`,
  `submission.exam_assignment_id` UNIQUE (single-attempt, FR-6).
- `Exam.exam_questions` carries `order_by="ExamQuestion.order"` on the
  relationship, so it always loads in exam order.

### Known gaps / caveats across the whole epic

- **NOTHING IN THIS EPIC HAS EVER BEEN EXECUTED.** T001–T020 were all
  authored without Python or Docker available. No test has run, no import
  has been resolved, no migration has been applied. **T090's first job is
  to bring up Postgres (`docker compose up`), run `alembic upgrade head`
  and `pytest`, and fix failures in place.** Treat every "passes" claim in
  every handoff as "written to pass".
- Highest-risk unverified runtime behaviours, in priority order:
  1. `await session.rollback()` + `async with session.begin():` in
     `submit_exam` — the autobegin interaction is reasoned-about, not
     observed. If it raises `InvalidRequestError: A transaction is already
     begun`, the fix is local to that line.
  2. `Submission.submitted_at` / `Answer.is_correct` are server-defaults.
     `submit_exam` deliberately **never reads `submitted_at` after the
     commit** (it is not in `SubmitExamResponse`) because that would be a
     lazy refresh and would raise `MissingGreenlet` in async. Keep it out
     of the POST response.
  3. The `IntegrityError` catch-and-rollback paths in `assign_exam`
     (T012), `create_user` (T010) and `submit_exam` (T020) — none has met
     a real Postgres unique violation.
  4. `selectinload` / `joinedload` behaviour in the async context
     (`Question.options`, `Exam.exam_questions`, `Submission.answers`,
     `Submission.exam_assignment`). Any missed eager load surfaces as
     `MissingGreenlet`, not as a silent N+1.
  5. The WARN-4 query-count assertion (`large == small`) is the most
     brittle test in the suite — it depends on identity-map state. If it
     fails by a constant offset, check the warm-up request before
     loosening it; the assertion that must survive is "does not grow with
     N".
- **Functional gaps, all deliberate and out of scope:** no `GET /exams`
  list-all; no `PATCH`/`DELETE` for exams or questions; no endpoint for a
  user to list *their own* assignments or submissions (they must be given
  the id); `create_exam([])` accepts an empty `question_ids` and such an
  exam can be assigned and submitted for a score of 0/0; multi-select
  questions are NTH-1 (deferred) — grading assumes exactly one correct
  option per question and takes the first if there are several; the
  "exactly one correct option" rule is enforced only at question-creation
  time (T011), not by a DB constraint.
- **`UserNotFoundError` is shared** by "user_id doesn't exist" and "user
  exists but `role != 'user'`" in `assign_exam` — both map to 404.

### Acceptance-criteria → test map for T090

| Criterion | Test |
|---|---|
| SC-2 grading | `tests/unit/test_grading.py` |
| FR-6 happy path | `tests/integration/test_submit_transaction.py::test_submit_grades_and_returns_breakdown` |
| CRIT-1 rollback | `...::test_failure_between_answer_inserts_rolls_back_everything` |
| WARN-2 409 | `...::test_double_submit_returns_409_not_500` |
| FR-7 owner view | `tests/integration/test_results_authz.py::test_owner_gets_their_own_score_and_breakdown` |
| CRIT-2 403 | `...::test_user_b_cannot_read_user_a_submission` |
| CRIT-2 admin not blocked | `...::test_admin_can_read_any_users_submission` |
| WARN-4 query count | `tests/integration/test_results_n_plus_1.py::test_list_submissions_query_count_is_constant_in_n` |

## Files Changed (T020)

Created:
- `app/application/use_cases/submit_exam.py`
- `app/application/use_cases/get_results.py`
- `app/api/v1/routers/submissions.py`
- `tests/unit/test_grading.py`
- `tests/integration/test_submit_transaction.py`
- `tests/integration/test_results_authz.py`
- `tests/integration/test_results_n_plus_1.py`

Modified:
- `app/main.py` (router wiring only)
- `.sdd/epics/exam-builder-base/020.md` (frontmatter: status closed)
