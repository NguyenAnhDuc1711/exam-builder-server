# Handoff: T002 — Domain entities + SQLAlchemy models + initial migration

## What Was Done

- **Domain entities** (`app/domain/entities/`, plain dataclasses, zero
  SQLAlchemy/Pydantic imports per AD-1): `user.py` (`User`, `Role`),
  `question.py` (`Question`, `Option` + `has_single_answer()` /
  `correct_option_id()` helpers for the "exactly one correct option" rule
  that cannot be a DB constraint), `exam.py` (`Exam`, `ExamAssignment`),
  `submission.py` (`Submission`, `Answer`). Re-exported from
  `app/domain/entities/__init__.py`.
- **SQLAlchemy 2.0 ORM models** (`app/infrastructure/db/models/`), async-
  compatible `DeclarativeBase` + `Mapped`/`mapped_column` style:
  `user.py`, `question.py` (Question/Option), `exam.py` (Exam/
  ExamQuestion/ExamAssignment), `submission.py` (Submission/Answer),
  `refresh_token.py`. 9 tables total.
- **`app/infrastructure/db/base.py`** (new, not in the task's file list but
  required): the shared `Base(DeclarativeBase)`. `models/__init__.py`
  imports every model module so `Base.metadata` is always complete.
- **`app/infrastructure/db/session.py`**: `create_async_engine(
  settings.DATABASE_URL, pool_pre_ping=True)`, `AsyncSessionLocal =
  async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)`,
  and an `async def get_session() -> AsyncGenerator[AsyncSession, None]`
  FastAPI dependency. It does **not** commit — the use case owns the
  transaction boundary (CRIT-1).
- **`alembic/versions/0001_initial.py`**: hand-written (no `--autogenerate`
  possible, see Warnings). `revision = "0001_initial"`,
  `down_revision = None`. Creates all 9 tables with FKs, indexes and both
  critical unique constraints; `downgrade()` drops them in reverse order.
- **`alembic/env.py`** (T001 file, minimally edited as T001 instructed):
  `target_metadata = Base.metadata` and `import app.infrastructure.db.models`.
  No other T001 file was touched — `app/core/config.py` already exposed
  everything `session.py` needed.
- **Tests** (unexecuted): `pytest.ini` (`pythonpath = .`,
  `asyncio_mode = auto`), `tests/conftest.py` (env priming + per-test
  `db_engine`/`session` fixtures), `tests/unit/test_schema_invariants.py`
  (9 tables, no org/tenant column, domain entities import no SQLAlchemy,
  both unique constraints present),
  `tests/integration/test_schema_constraints.py` (duplicate assignment →
  IntegrityError, second submission → IntegrityError, question delete
  cascades to options), `tests/integration/test_migrations.py`
  (`upgrade head` / `downgrade base` / no tenant columns in the migrated DB).

## Decisions Made

- **Table names are all singular**, exactly as the task spec lists them:
  `user, question, option, exam, exam_question, exam_assignment,
  submission, answer, refresh_token`.
  **`refresh_token` is singular — AD-2's prose says `refresh_tokens`.**
  Singular wins for consistency with the other 8 tables; see Warnings.
- `user` and `order` are **reserved SQL words**. SQLAlchemy and Alembic
  quote them automatically, so the ORM works; any *hand-written* SQL must
  spell them `"user"` / `"order"`.
- **`exam_question` uses a composite PK `(exam_id, question_id)`** (the
  spec allowed composite PK *or* surrogate + unique). This gives the
  no-duplicate-question-per-exam guarantee for free; `order` is a plain
  NOT NULL integer (no unique constraint on `(exam_id, order)` — not
  required by the spec).
- **`submission.score` is `Integer NOT NULL server_default 0`**, not
  nullable. T020 can insert the Submission, flush for its id, insert the
  Answers, then set `score` — all inside one transaction — without ever
  leaving a NULL score for readers.
- **`answer.selected_option_id` is nullable** = the question was left
  unanswered (such an answer is never correct). `answer.question_id` and
  `answer.selected_option_id` use the default RESTRICT (no cascade), so a
  question/option that has been answered cannot be silently deleted.
- **Cascades**: `option → question`, `exam_question → exam/question`,
  `exam_assignment → exam/user`, `submission → exam_assignment`,
  `answer → submission`, `refresh_token → user` are all
  `ON DELETE CASCADE`. ORM relationships that mirror a cascade use
  `passive_deletes=True` so the DB does the work.
- **`user.role`** is `String(20)` + `CHECK (role IN ('admin','user'))`
  (named `ck_user_role`) rather than a native PG ENUM — enums are painful
  to alter in Alembic and the check gives the same guarantee.
- **No `created_at`/`updated_at` columns** anywhere they were not asked
  for. Only `exam_assignment.assigned_at` and `submission.submitted_at`
  exist, both `TIMESTAMPTZ NOT NULL DEFAULT now()`.
- **No `organization_id`, no tenant concept** (NFR-3) — asserted by a test
  over `Base.metadata` *and* by a test over `information_schema` after
  migrating.

## Files Changed

Created:
- `app/domain/entities/{__init__,user,question,exam,submission}.py`
- `app/infrastructure/db/base.py`, `app/infrastructure/db/session.py`
- `app/infrastructure/db/models/{__init__,user,question,exam,submission,refresh_token}.py`
- `alembic/versions/0001_initial.py`
- `pytest.ini`, `tests/__init__.py`, `tests/conftest.py`,
  `tests/unit/{__init__,test_schema_invariants}.py`,
  `tests/integration/{__init__,test_migrations,test_schema_constraints}.py`

Modified:
- `alembic/env.py` (target_metadata + models import only)
- `.sdd/epics/exam-builder-base/002.md` (frontmatter: status closed)

## Schema Reference for T003 (refresh token repository)

Model `app.infrastructure.db.models.refresh_token.RefreshToken`,
table **`refresh_token`** (singular!). Exact columns:

| column       | type            | constraints                                  |
|--------------|-----------------|----------------------------------------------|
| `id`         | `Integer`       | PK, autoincrement                            |
| `user_id`    | `Integer`       | FK `user.id` ON DELETE CASCADE, NOT NULL, indexed |
| `token_hash` | `String(64)`    | NOT NULL, **UNIQUE** (unique index `ix_refresh_token_token_hash`) |
| `family_id`  | `String(36)`    | NOT NULL, indexed                            |
| `revoked`    | `Boolean`       | NOT NULL, server_default `false`             |
| `expires_at` | `DateTime(timezone=True)` | NOT NULL                           |

- `token_hash` holds the **SHA-256 hex digest** (`hashlib.sha256(token
  .encode()).hexdigest()` → exactly 64 chars). Never store plaintext (R-6).
- `family_id` is a **UUID4 string** (`str(uuid.uuid4())`, 36 chars incl.
  hyphens) — not a native UUID column, so compare/store as `str`.
- There is **no `created_at`** column and **no domain entity** for refresh
  tokens (AD-2: infrastructure concern only).
- Revoking a family = `UPDATE refresh_token SET revoked = true WHERE
  family_id = :family_id`.
- The `user` table model is `app.infrastructure.db.models.user.User` with
  columns `id, email (unique), password_hash, role` — `role` is a plain
  string constrained to `'admin'`/`'user'`; the domain `Role` alias lives
  in `app/domain/entities/user.py`.

## Warnings for Next Task (T003)

- **Nothing in this task was executed.** No Python and no Docker in this
  environment (same as T001): `alembic upgrade head`, `pytest`, and even
  `import app.infrastructure.db.models` were never run. T003 (or whoever
  first has a real environment) should run, before building on this:
  1. `docker-compose up -d postgres`
  2. `alembic upgrade head` and then `alembic downgrade base`
  3. `createdb exam_builder_test` (or `TEST_DATABASE_URL=...`) then `pytest`
  Treat a failure here as a T002 defect and fix it in place.
- **`refresh_token` vs `refresh_tokens` naming**: epic AD-2's prose says
  `refresh_tokens`. The implemented table is **`refresh_token`**. If the
  epic doc matters more than consistency, rename in `refresh_token.py` +
  `0001_initial.py` *before* the migration is applied anywhere — it is a
  two-line change now and a new migration later.
- **`autoincrement`/`Identity`**: `sa.Integer` + `primary_key=True` renders
  as `SERIAL` on PostgreSQL. If the team prefers `GENERATED BY DEFAULT AS
  IDENTITY`, change it now while there is still only one migration.
- `app/core/config.py` still instantiates `settings = Settings()` at import
  time with no defaults, and **`app/infrastructure/db/session.py` creates
  the engine at import time from `settings.DATABASE_URL`**. Importing
  `session.py` (directly or via a router) therefore requires a valid
  `DATABASE_URL` in the environment. `tests/conftest.py` handles this by
  force-setting `DATABASE_URL` from `TEST_DATABASE_URL` *before* any `app.`
  import — keep that ordering when you add fixtures.
- Test DB defaults to
  `postgresql+asyncpg://exam_builder:exam_builder@localhost:5432/exam_builder_test`;
  it is **dropped and recreated per test**, so never point it at a dev DB.
- `alembic/versions/.gitkeep` is still present next to the real migration;
  harmless, delete whenever.
- `tests/` is a real package (`__init__.py` in `tests/`, `tests/unit/`,
  `tests/integration/`) because `test_migrations.py` imports
  `tests.conftest`. Keep the `__init__.py` files if you add subfolders.
- Migration tests are **synchronous on purpose** — `alembic/env.py` calls
  `asyncio.run()` itself and will raise if invoked from inside a running
  event loop (i.e. from an `async def` test).
