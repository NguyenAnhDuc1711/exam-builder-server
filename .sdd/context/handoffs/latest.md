# Handoff: T010 — Admin user management

## What Was Done

- **`app/application/use_cases/create_user.py`**: `create_user(session, email,
  password, role="user") -> User`. Checks `email` uniqueness with a `SELECT`,
  raises `EmailAlreadyExistsError(email)` (defined in the same module) if
  taken, otherwise hashes `password` with `hash_password` (T003), inserts a
  `User`, `commit()`s, and returns the ORM row.
- **`app/api/v1/routers/users.py`**: `router = APIRouter(prefix="/users",
  tags=["users"])` with `POST /users`, gated by
  `dependencies=[Depends(require_role("admin"))]` (route-gate shape — the
  handler doesn't need the caller). Request/response schemas are defined
  inline in this file (no `app/api/v1/schemas/users.py`; T010's file list
  didn't include one and nothing else needed it):
  - `CreateUserRequest{email: str, password: str}` — **no `role` field**.
    `password` has `Field(max_length=72)` (bcrypt silently truncates beyond
    72 bytes — flagged in T003's handoff as "the natural place to add this").
  - `UserResponse{id, email, role}` with `model_config =
    {"from_attributes": True}`, built straight from the returned ORM `User`
    — `password_hash` is never on the model, so it cannot leak into the
    response.
  - On `EmailAlreadyExistsError` the router raises `HTTPException(409,
    "Email already registered")`.
- **Tests** (unexecuted): `tests/integration/test_admin_users.py` — admin
  creates a user (201, `password_hash`/`password` absent from body, DB row
  has `role="user"` and a hashed, not plaintext, password), non-admin gets
  403, no token gets 401, duplicate email gets 409. Same ASGI-through-httpx
  pattern as `tests/integration/test_auth_rotation.py`, with a throwaway
  `FastAPI()` mounting only `/auth` (to log in) and `/users` (under test) and
  `get_session` overridden to the per-test `session` fixture.

## Decisions Made

- **No `role` field on `CreateUserRequest` at all**, not just a default.
  010.md is explicit that admins must not be able to mint other admins
  through this endpoint in v1; the use case still accepts a `role` parameter
  (default `"user"`) for testability/reuse, but the API surface never
  forwards a caller-supplied value — there is no code path from the request
  body to `role`.
- **`email: str`, not `EmailStr`** — matches `app/api/v1/schemas/auth.py`;
  `email-validator` still isn't a dependency.
- **Uniqueness check is check-then-insert, not atomic.** `user.email` has a
  DB-level unique index (T002), so a genuine race would surface as an
  `IntegrityError` on `commit()`, not a clean 409. Left as-is: same class of
  accepted gap as T003's documented concurrency notes, and out of scope for
  a single-admin v1. Flagged here rather than silently ignored.
- **`app/main.py` was touched** (outside the task's stated file list) to add
  `app.include_router(users.router)` — the same "integration edit" T003 made
  for `auth.router`. Without it the endpoint does not exist in the running
  app and the verification checklist (`/openapi.json` route listing) cannot
  pass. This is the only file touched outside
  `app/api/v1/routers/users.py` / `app/application/use_cases/create_user.py`
  / test files.

## Files Changed

Created:
- `app/application/use_cases/create_user.py`
- `app/api/v1/routers/users.py`
- `tests/integration/test_admin_users.py`

Modified:
- `app/main.py` (router wiring only, see above)
- `.sdd/epics/exam-builder-base/010.md` (frontmatter: status closed)

## Warnings for Next Task

- **Nothing was executed.** Still no Python/Docker in this environment.
  `pytest`, `alembic upgrade head`, and `import app` have never run across
  T001–T010. Run the full suite and fix failures in place as defects before
  trusting any of this.
- **User model fields (for T012, exam assignment, which needs to reference
  existing users by id):** `app.infrastructure.db.models.user.User` —
  `id: int` (PK), `email: str` (unique, indexed), `password_hash: str`
  (never expose), `role: str` (CHECK constraint, exactly `"admin"` or
  `"user"`). No `created_at`/timestamps, no soft-delete, no
  `organization_id` (NFR-3, single-tenant). To list assignable users, query
  `User` directly (e.g. `select(User.id, User.email).where(User.role ==
  "user")`) — there is no existing repository/list endpoint for users, only
  creation.
- **`POST /users` returns `201` with `{id, email, role}`** — use that shape
  if T012 needs to display/validate a user reference client-side.
- **Duplicate-email race is unhandled** (see Decisions above) — if T012 or
  anything else creates users concurrently, add either a `try/except
  IntegrityError` around the `commit()` in `create_user()` or a
  `SELECT ... FOR UPDATE`. Not needed for the current admin-only, one-at-a-
  time usage pattern.
- Reuses the same test conventions as T003: throwaway `FastAPI()` app for
  route-level isolation, `get_session` overridden to the `session` fixture,
  `session.expire_all()` before any post-request DB assertion.
