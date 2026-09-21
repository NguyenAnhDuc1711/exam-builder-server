# Handoff: T001 — Project scaffolding + Docker Compose + Alembic init

## What Was Done

- Created the Clean Architecture skeleton under `app/` per epic AD-1:
  `domain/{entities,repositories}`, `application/{use_cases,ports}`,
  `infrastructure/{db/{models,repositories},auth,storage}`,
  `api/v1/{routers,schemas}`, `core/`. Every package has an empty
  `__init__.py`.
- `app/core/config.py`: Pydantic v2 `BaseSettings` (`pydantic-settings`)
  reading `DATABASE_URL`, `JWT_SECRET_KEY`, `JWT_ACCESS_EXPIRE_MINUTES`
  (default 1440), `JWT_REFRESH_EXPIRE_DAYS` (default 7),
  `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`
  from env / `.env`. Required fields have no defaults so startup fails
  fast if misconfigured. A module-level `settings = Settings()` singleton
  is exported for import elsewhere.
- `app/main.py`: empty FastAPI app + `GET /health` -> `{"status": "ok"}`.
  No other routes/business logic added, per task scope.
- `Dockerfile`: `python:3.12-slim`, installs `requirements.txt`, runs
  `uvicorn app.main:app --host 0.0.0.0 --port 8000`.
- `docker-compose.yml`: `postgres` (image `postgres:16`, named volume,
  `pg_isready` healthcheck), `api` (build from Dockerfile, `env_file: .env`,
  `depends_on: postgres: condition: service_healthy`), `pgadmin`
  (`dpage/pgadmin4`, port `5050:80`).
- `requirements.txt`: fastapi, uvicorn[standard], sqlalchemy[asyncio],
  asyncpg, alembic, pydantic, pydantic-settings, python-jose[cryptography],
  passlib[bcrypt], cloudinary, pytest, pytest-asyncio, httpx.
- Alembic initialized at repo root (`alembic.ini`, `alembic/env.py`,
  `alembic/script.py.mako`, `alembic/README`, `alembic/versions/.gitkeep`)
  using the **async** template (matches SQLAlchemy 2.0 async engine, not
  the plain sync template `alembic init alembic` would generate).
  `alembic/env.py` overrides `sqlalchemy.url` at runtime from
  `app.core.config.settings.DATABASE_URL` — single source of truth for the
  connection string. `target_metadata = None` for now; T002 must set it to
  the shared declarative `Base.metadata`.
- `.env.example`: lists every variable consumed by `config.py` and by
  `docker-compose.yml` (`POSTGRES_*`, `PGADMIN_DEFAULT_*`). No real
  secrets — placeholder/dev-friendly defaults only.
- `.gitignore`: added (`.env`, `__pycache__/`, `.venv/`, `*.pyc`,
  `.pytest_cache/`, etc.) — did not exist before this task; needed so a
  real `.env` never gets committed.

## Decisions Made

- **Async SQLAlchemy + asyncpg**, per task instructions and epic's
  "FastAPI + PostgreSQL/SQLAlchemy" stack — enables non-blocking I/O
  under FastAPI's async request handlers, avoids mixing sync/async DB
  drivers. `DATABASE_URL` in `.env.example` uses the
  `postgresql+asyncpg://` scheme.
- **Alembic async template** (`alembic init -t async` equivalent, hand-
  written since no local Python/Alembic CLI was available in this
  environment — see Warnings) rather than the sync default, since a sync
  `alembic.ini`/`env.py` would not accept an `asyncpg` URL without extra
  driver-swapping hacks.
- **`requirements.txt` over `pyproject.toml`** — task allowed either;
  chose the simpler, boilerplate-free option since there's no package
  distribution need yet (Karpathy: simplicity first).
- **No `app/infrastructure/db/session.py` created yet** — AD-1 shows it
  in the target layout, but T001's explicit implementation steps don't
  call for it and there are no models to bind a session/engine to yet.
  Left as a T002 responsibility (see Warnings below).
- **No `app/api/dependencies.py` created** — AD-1 lists it, but it has no
  content until `require_role`/`get_current_user` exist in T003. Skipped
  to keep this task to directory-structure + infra only.

## Files Changed

- `app/__init__.py`, `app/main.py`
- `app/core/__init__.py`, `app/core/config.py`
- `app/domain/__init__.py`, `app/domain/entities/__init__.py`,
  `app/domain/repositories/__init__.py`
- `app/application/__init__.py`, `app/application/use_cases/__init__.py`,
  `app/application/ports/__init__.py`
- `app/infrastructure/__init__.py`, `app/infrastructure/db/__init__.py`,
  `app/infrastructure/db/models/__init__.py`,
  `app/infrastructure/db/repositories/__init__.py`,
  `app/infrastructure/auth/__init__.py`,
  `app/infrastructure/storage/__init__.py`
- `app/api/__init__.py`, `app/api/v1/__init__.py`,
  `app/api/v1/routers/__init__.py`, `app/api/v1/schemas/__init__.py`
- `Dockerfile`, `docker-compose.yml`, `requirements.txt`, `.env.example`,
  `.gitignore`
- `alembic.ini`, `alembic/env.py`, `alembic/script.py.mako`,
  `alembic/README`, `alembic/versions/.gitkeep`
- `.sdd/epics/exam-builder-base/001.md` (frontmatter: status closed)

## Warnings for Next Task (T002)

- **No Python or Docker was available in this execution environment** —
  `python3`/`python`/`py` all resolved to the Windows Store stub, and
  `docker`/`docker-compose` were not on PATH. None of this was run:
  `pip install`, `python -c "import app.main"`, `docker-compose up`,
  `alembic current`. Everything was written by hand, cross-checked
  against the standard `alembic init -t async` output and FastAPI/
  pydantic-settings v2 APIs from memory. **T002 (or whoever has a real
  Python/Docker environment) should run `docker-compose up -d`,
  `curl localhost:8000/health`, and `alembic current` before trusting
  this scaffold further** — that's this task's acceptance criteria and
  it is unverified.
- `app/core/config.py` instantiates `settings = Settings()` at **import
  time** with no defaults for `DATABASE_URL`, `JWT_SECRET_KEY`,
  `CLOUDINARY_*`. Any import of `app.main` (including under pytest) will
  raise a `pydantic.ValidationError` unless a `.env` file or equivalent
  env vars are present. T002+ test suites need a `.env` (copied from
  `.env.example`) or a pytest fixture that sets these env vars **before**
  `app.core.config` is imported.
- **T002 must create `app/infrastructure/db/session.py`** with the async
  engine/session pattern (`create_async_engine(settings.DATABASE_URL)`,
  `async_sessionmaker(engine, expire_on_commit=False)`) and set
  `alembic/env.py`'s `target_metadata = Base.metadata` (currently `None`)
  once the declarative `Base` and ORM models exist — otherwise
  `alembic revision --autogenerate` will not detect any tables.
- Naming convention to follow for consistency: entity/model files are
  singular (`question.py`, `exam.py`), matching the epic's file list
  (`app/domain/entities/*.py`, `app/infrastructure/db/models/*.py`).
- `alembic/versions/` is empty except for `.gitkeep` (git doesn't track
  empty dirs) — remove `.gitkeep` once the first real migration lands, or
  leave it; either is harmless.
