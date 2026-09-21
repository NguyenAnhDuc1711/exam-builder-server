# T090 Verification Report — exam-builder-base

**Method:** static/manual code review only. **No Python, Docker, or database
were available in this execution environment.** Nothing in this report was
obtained by running `pytest`, `docker-compose up`, `alembic upgrade head`, or
importing any module — every claim below is "verified by reading the actual
source," never "verified by executing it." Every prior task handoff
(T001–T020) makes the same disclaimer; that chain is unbroken through T090.

## What was done

1. Read every task file `001.md`–`020.md` in `.sdd/epics/exam-builder-base/`
   and opened every file each one's `files:` frontmatter claims to have
   created — all exist and match their described contents (see per-file
   notes below).
2. Wrote `tests/integration/test_e2e_flow.py`: one sequential test driving
   the real `app.main.app` (all 5 routers, not a throwaway subset) through
   seed-admin → admin login → create user → create 2 questions (one with an
   image, mocked Cloudinary) → assemble exam → assign → user login → submit
   (one right / one wrong, score checked) → duplicate submit → 409 →
   user reads own result → admin reads the same result via the exam listing
   and the two are asserted equal → a third, unrelated user is confirmed
   locked out of both read endpoints (CRIT-2). Each step consumes the
   previous step's response body (ids), never a hard-coded id.
3. Walked the epic.md Traceability Matrix row by row (table below).
4. Cross-checked every later task's assumed import against what the earlier
   task actually created (table below) — this is the part most likely to
   catch integration mistakes between 7 independently-authored pieces.
5. `grep -rn "TODO\|FIXME" app/` — **zero matches.**
6. Confirmed `app/main.py` registers all 5 routers: `auth`, `users`,
   `questions`, `exams`, `submissions` (lines 3, 9–13).

## Traceability Matrix — row-by-row verification

| Req | Claimed coverage | Verified by reading | Verdict |
|---|---|---|---|
| FR-1 Auth + refresh rotation | T003, `test_auth_rotation.py` | `app/infrastructure/auth/jwt_service.py` implements family-based rotation + reuse detection exactly as AD-2 describes; `app/api/v1/routers/auth.py` commits even on the `RotationError` path (load-bearing — see Findings). Tests cover login, rotation, reuse burns the whole family, independent families, no-plaintext-storage. | Confirmed |
| FR-2 Admin user mgmt | T010, `test_admin_users.py` | `POST /users` gated by `require_role("admin")`; `create_user` always passes `role="user"` from the router regardless of any client input (no `role` field on `CreateUserRequest`). | Confirmed |
| FR-3 Question bank + image | T011, `test_questions.py` + `test_question_upload_failure.py` | `create_question.py` validates exactly-one-correct-option and sniffs real magic bytes (not the client `Content-Type`) before ever calling `image_storage.upload`; Cloudinary failure path returns 201 with `image_url=None` + warning. | Confirmed |
| FR-4 Exam assembly | T012, `test_exam_assembly.py` | `create_exam` checks all `question_ids` exist in one `SELECT ... IN (...)` before any `session.add`; order preserved as 0-based `ExamQuestion.order`. Missing-id test asserts **zero** partial rows after a 404. | Confirmed |
| FR-5 Exam assignment | T012, `test_exam_assignment.py` | `assign_exam` checks exam + user existence, rejects `role != "user"` targets, relies on DB `UniqueConstraint` for the duplicate case (caught `IntegrityError` → 409). | Confirmed |
| FR-6 Submission + grading | T020, `test_grading.py` + `test_submit_transaction.py` | `grade()` is pure and matches by `question_id`, not position (dedicated shuffle test). `submit_exam` wraps the `Submission` + all `Answer` inserts in one `session.begin()` block; `IntegrityError` → `AlreadySubmittedError` → 409. | Confirmed |
| FR-7 Results viewing | T020, `test_results_authz.py` + `test_results_n_plus_1.py` | `get_submission` is a two-query design: query 1 fetches **only** the owner's `user_id`, decides 403/404, and only query 2 (unreachable if unauthorized) loads score/answers. `list_submissions_for_exam` eager-loads with `selectinload`/`joinedload`; query-count test compares an exam with 2 vs 6 submissions. | Confirmed |
| NFR-1 Token rotation security | T003 | Same evidence as FR-1; `_revoke_family` bulk-UPDATEs every row in the family including never-used ones. | Confirmed |
| NFR-2 Cloudinary failure tolerance | T011 | `UploadError` is caught in the use case, never propagated as 500; question is still persisted. `CloudinaryImageStorage.upload` re-wraps every SDK exception as `UploadError`. | Confirmed |
| NFR-3 Single-tenant | T002 | `grep`-level check confirms no `organization`/`tenant` column in any of the 9 tables (`app/infrastructure/db/models/*.py`) or in `0001_initial.py`. `test_schema_invariants.py` and `test_migrations.py::test_migrated_schema_has_no_multi_tenant_columns` both assert this — the latter against the **actual migrated** schema, not just ORM metadata. | Confirmed |
| NFR-4 Docker Compose deploy | T001 | `docker-compose.yml` has 3 services, `api` depends on `postgres`'s `service_healthy` condition, `/health` returns `{"status":"ok"}` without touching the DB. **Caveat, see Findings #3**: nothing in the compose file or `Dockerfile` ever runs `alembic upgrade head`. | Confirmed **for the AC as literally written** (health check only); real usability caveat noted below |

11/11 MUST FR+NFR rows have a real, existing, matching test file — none is
"named but empty" or "named but testing something else."

## Cross-task import/assumption consistency (the actual point of T090)

Checked every symbol a later task imports against the file the earlier task
that "owns" it actually produced:

- `app/api/dependencies.py` exports exactly `get_current_user` and
  `require_role(role)`, matching every later router's import
  (`auth.py` doesn't use it — it's the only unauthenticated router, by
  design; `users.py`, `questions.py`, `exams.py`, `submissions.py` all do).
  `require_role` checks `current_user.role` from the **DB row** (re-fetched
  via `get_current_user`), not the JWT claim — matches T003's own docstring
  promise that a role change takes effect without waiting for token expiry.
- `app/infrastructure/db/models/user.py`'s `User` has exactly `id`, `email`,
  `password_hash`, `role` — every field every later task assumes
  (`create_user`, `get_current_user`, `assign_exam`'s `user.role != "user"`
  check, every test's `User(email=..., password_hash=hash_password(...),
  role=...)` constructor call) is present, with the right names.
- `app/infrastructure/db/models/__init__.py` re-exports all 9 model classes
  by name (`Exam, ExamAssignment, ExamQuestion, Option, Question,
  RefreshToken, Submission, Answer, User`) — matches
  `tests/integration/test_schema_constraints.py`'s bare
  `from app.infrastructure.db.models import (...)`.
- `ExamQuestion.order` and the `Exam.exam_questions` relationship's
  `order_by="ExamQuestion.order"` (in `app/infrastructure/db/models/exam.py`)
  are exactly what T020's `submit_exam` relies on for "exam order" and what
  T012's assembly test relies on for round-tripping a shuffled
  `question_ids` list.
- `submission.exam_assignment_id` UNIQUE (T002) is exactly the constraint
  T020's WARN-2 catch depends on, and it is present in **both** the ORM
  model and `0001_initial.py` (hand-checked column-by-column against each
  other — they match exactly, including index names).
- `ImageStoragePort.upload(file: bytes, content_type: str) -> str` (T011's
  own port) is the exact signature `CloudinaryImageStorage.upload` and
  `create_question`'s call site both use — no drift.
- Every integration test file's `get_session` override targets the same
  `app.infrastructure.db.session.get_session` the real routers depend on —
  no test accidentally overrides a different callable that would silently
  no-op.
- `app/main.py` imports `auth, exams, questions, submissions, users` from
  `app.api.v1.routers` — all five modules exist with a module-level `router`
  object; registration order does not collide (`submissions.py`'s own
  docstring explicitly reasons about this against `exams.py`).

**No import-path or shape mismatch was found between any two tasks.** This
is the main finding: despite being authored by 7 separate passes, the
interfaces line up exactly, including field names, exception classes caught
by name, and response-shape assumptions baked into later tests (e.g.
`test_results_authz.py` asserting `response.json() == {"detail":
"Forbidden"}` matches `submissions.py`'s `HTTPException(..., detail=
"Forbidden")` byte-for-byte).

## Real findings

1. **No path from a clean `docker-compose up -d` to a working schema.**
   Neither `docker-compose.yml` nor `Dockerfile` ever invokes `alembic
   upgrade head`. `/health` doesn't touch the DB, so the T001 acceptance
   criterion ("curl health → 200 in 60s") and the epic's SC-5 will pass
   literally as written — but every other endpoint would 500 against a
   freshly-provisioned Postgres because none of the 9 tables exist until
   someone runs the migration by hand. This is consistent with T001.md's
   AC as written (migration-on-boot was never in scope for any task), but
   it is a real gap between "the smoke test passes" and "the app actually
   works after `docker-compose up`." Recommended fix (not made here, since
   T090 is not the place to patch new behavior): either an `entrypoint.sh`
   that runs `alembic upgrade head` before `uvicorn`, or a documented manual
   step.
2. **No route creates the first admin.** `POST /users` requires an existing
   admin's token, and there is no public sign-up, no seed script, and no
   Alembic data migration that inserts a bootstrap admin. Every test in the
   suite (and the new `test_e2e_flow.py`) works around this by inserting a
   `User(role="admin")` directly through the ORM session — which is exactly
   what a real deployment would have to do by hand (e.g. a one-off `psql`
   insert or a manage.py-style script), and nothing in the repo documents
   that step. Out of scope per the task specs (T010 explicitly says "no
   public sign-up route"), but worth flagging as a real first-run blocker.
3. **passlib + bcrypt version pin risk.** `requirements.txt` pins
   `passlib[bcrypt]>=1.7,<2` but does not separately pin the `bcrypt`
   package version. `passlib` 1.7.4's bcrypt backend probe is known to log
   a spurious `(trapped) error reading bcrypt version` against `bcrypt>=4.1`
   (a widely-reported passlib/bcrypt interop issue in the wider ecosystem);
   it is usually harmless (falls back correctly) but has, in some
   passlib/bcrypt combinations, raised at import time. This was not
   something any task's code review could have caught by reading source —
   it only surfaces when `pip install` actually resolves a `bcrypt`
   version, which never happened in this environment. Flagging so whoever
   runs the real `pip install` checks for it early rather than mid-debug.
4. **`app/domain/entities/*.py` is mostly inert.** AD-1 states the domain
   layer isolates business rules from persistence. In practice, every use
   case (`create_user`, `assemble_exam`, `assign_exam`, `submit_exam`,
   `get_results`) operates directly on the SQLAlchemy models, not the
   dataclasses in `app/domain/entities/`. The one exception is
   `Question`/`Option` in `create_question.py`, which really does use
   `QuestionEntity.has_single_answer()` for the validation rule. This is a
   pre-existing architectural inconsistency documented nowhere as a
   deviation (T002's handoff doesn't call it out), not a bug — nothing
   breaks — but AD-1's stated benefit ("business logic testable independent
   of SQLAlchemy") is only realized for the one rule that actually uses it.
   No FR/NFR depends on the unused entities being wired in, so this is not
   blocking.
5. **`score` is a raw count, not a ratio**, exactly as T020's handoff
   Part 4 documents (`epic.md`/`020.md` text literally says "số câu đúng /
   tổng số câu" but the stored `score` column and the API field are the
   correct-answer count with `total_questions` alongside it). Confirmed by
   reading `submission.py`'s `score: Mapped[int]` and every response schema
   — this is a documented, deliberate deviation, not an oversight, and the
   ratio is always exactly recoverable from the two numbers returned. Not a
   defect, listed here only because the task literally didn't match spec
   text and a reviewer should know that was a conscious call, already
   written up by T020 itself.

No other discrepancy, TODO, stub, or contradiction between any two tasks'
assumptions was found.

## What remains genuinely unverified (requires real execution)

Everything below is structurally sound by reading, but **has never run**:

- **The full test suite has never executed.** Every `assert` in every test
  file listed in this report is unexecuted Python. A syntax error, a
  fixture ordering bug, or a wrong assertion would not have been caught by
  this review process — only by actually running `pytest tests/ -v`.
- **`await session.rollback()` immediately before `async with
  session.begin():`** in `submit_exam` (the interaction the T020 handoff
  flags as its #1 risk) — the reasoning that `get_current_user`'s
  autobegin + a no-write `rollback()` is safe to precede a fresh
  `session.begin()` has never been observed against a real asyncpg
  connection. If SQLAlchemy's autobegin semantics differ subtly from what
  the code assumes, this raises `InvalidRequestError` and the fix is local
  to that one line — but it is untested.
- **Every `selectinload`/`joinedload` path** (`Question.options`,
  `Exam.exam_questions`, `Submission.answers`, `Submission.exam_assignment`)
  has never been exercised under `asyncpg`. A missed eager-load surfaces as
  `MissingGreenlet`, not a clean failure — this class of bug is invisible
  to static reading.
- **Every `IntegrityError` catch-and-rollback path** (`assign_exam`,
  `create_user`, `submit_exam`) has never met a real Postgres unique
  violation. The exception type and the rollback-then-raise pattern are
  correct by inspection, but no test has actually forced Postgres to raise
  one.
- **The migration itself** (`0001_initial.py`) has never run against a real
  Postgres. It was hand-written to mirror the ORM models column-by-column
  (verified above, and they do match), but `alembic upgrade head` /
  `downgrade base` have never executed, so DDL-level issues (reserved-word
  quoting for `"user"` and `"order"`, constraint name collisions, etc.)
  remain theoretical.
- **`docker-compose up -d` has never run.** The 60-second healthcheck
  window, the `depends_on: condition: service_healthy` wiring, and the
  `pg_isready` check are correct by reading, not by observation.
- **The new `tests/integration/test_e2e_flow.py`** — written to the same
  ASGI-through-httpx pattern as every other integration test in this repo
  and checked line-by-line against the real request/response schemas of
  all 5 routers, but it has never been run either. It is the highest-value
  test to run first once Python/Docker are available, since a failure in
  it likely means an inter-task integration bug that individual task test
  files wouldn't catch (each of those only exercises its own router subset).
- **The WARN-4 query-count test** (`test_results_n_plus_1.py`) is flagged by
  T020's own handoff as the most brittle assertion in the suite (large ==
  small, not just "doesn't grow") — genuinely worth watching first if
  anything is going to be a false failure.

## Bottom line

By reading every line of `app/`, every test file, both migration and ORM
schema definitions, and cross-referencing every import a later task made
against what an earlier task actually produced: **the codebase is
internally consistent.** No task assumed a symbol, field, or exception name
that a dependency didn't actually provide. All 11 MUST FR/NFR rows in the
Traceability Matrix have a real, matching, existing test. `app/` has zero
TODO/FIXME. All 5 routers are registered in `app/main.py`.

**None of this was executed.** This report is not a substitute for actually
running `pip install -r requirements.txt`, `docker-compose up -d`, `alembic
upgrade head`, and `pytest tests/ -v --tb=short` in an environment that has
Python and Docker. That run is required before this epic can be considered
verified, and it is likely (per the T020 handoff's own risk list) to surface
at least one small issue in the transaction/autobegin interaction or in the
async eager-loading paths — both classes of bug that only manifest at
runtime and cannot be ruled out by code review alone.
