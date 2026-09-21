# Handoff: T003 — Auth: JWT access/refresh + rotation + reuse detection

## What Was Done

- **`app/core/security.py`**: `hash_password(password)` / `verify_password(
  password, password_hash)` (passlib bcrypt `CryptContext`) and
  `hash_token(token) -> str` (SHA-256 hex, 64 chars). Two deliberately
  different primitives — bcrypt is slow/salted for low-entropy passwords,
  SHA-256 is fast/deterministic so a high-entropy refresh token can be found
  by an indexed equality match. `verify_password` returns `False` (instead of
  raising) on a malformed stored hash.
- **`app/application/ports/token_service.py`**: `TokenPair(NamedTuple)` with
  `.access_token` / `.refresh_token`, `RotationError(Exception)`, and the
  abstract `TokenServicePort` with `create_token_pair` / `rotate`.
- **`app/infrastructure/auth/jwt_service.py`**: `JwtTokenService(session)`
  implementing the port, plus module-level `JWT_ALGORITHM = "HS256"`,
  `decode_access_token(token) -> dict` and a re-export of `jose.JWTError`.
  - Access token = signed JWT `{sub: str(user_id), role, iat, exp}`,
    `exp = now + JWT_ACCESS_EXPIRE_MINUTES` (1440 = 24h).
  - Refresh token = `secrets.token_urlsafe(48)` — an **opaque random string,
    not a JWT**. Only `hash_token(...)` of it is written to
    `refresh_token.token_hash`; the plaintext exists once, in the response.
  - `create_token_pair` starts a new `family_id = str(uuid.uuid4())`.
  - `rotate(refresh_token)`: look up by hash →
    **not found** → `RotationError` (no family to burn);
    **`revoked=True`** → `UPDATE refresh_token SET revoked=true WHERE
    family_id=:fid` (the whole family, including the newest never-used
    token) then `RotationError`;
    **`expires_at <= now`** → `RotationError`, family left alone (expiry is
    not an attack signal and nothing in the family is usable anyway);
    **valid** → old row `revoked=True`, new row inserted with the *same*
    `family_id`, new pair returned.
  - The service only `flush()`es, never `commit()`s (CRIT-1).
- **`app/api/v1/schemas/auth.py`** (new, not in the task's file list):
  `LoginRequest{email,password}`, `RefreshRequest{refresh_token}`,
  `TokenPairResponse{access_token,refresh_token,token_type="bearer"}`.
- **`app/api/v1/routers/auth.py`**: `router = APIRouter(prefix="/auth")` with
  `POST /auth/login` and `POST /auth/refresh`, both 401 on failure with an
  intentionally vague `detail`.
- **`app/api/dependencies.py`**: `get_current_user` and `require_role`.
- **`app/main.py`** (T001 file, **integration edit**): now does
  `app.include_router(auth.router)`. Routers mount at the **root**, with no
  `/api/v1` prefix — T010's verification checklist pins the public paths as
  `/auth/login` and `/auth/refresh`, and T010/T011/T012 as `/users`,
  `/questions`, `/exams`. Follow that; put your router module under
  `app/api/v1/routers/` but give it a root-level `prefix`.
- **Tests** (unexecuted): `tests/unit/test_security.py` (bcrypt salting,
  SHA-256 shape, the two schemes are distinct) and
  `tests/integration/test_auth_rotation.py` (login success + `exp - iat ==
  86400`, wrong password → 401, unknown email → 401, rotation invalidates the
  old token, **reuse burns the whole family including the unused newest
  token**, a second login is an independent family, DB-level assertion that
  `token_hash` is never the plaintext, `require_role("admin")` → 403 for a
  normal user / 200 for an admin, missing-or-garbage bearer → 401).

## API for T010 / T011 / T012 (the important part)

```python
from app.api.dependencies import get_current_user, require_role
from app.infrastructure.db.models.user import User   # what they return

# Signatures
async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(HTTPBearer(auto_error=False)),
    session: AsyncSession = Depends(get_session),
) -> User: ...

def require_role(role: str) -> Callable[..., Awaitable[User]]: ...
```

Two usage shapes:

```python
# 1. Gate the route, ignore the caller:
@router.post("/users", status_code=201,
             dependencies=[Depends(require_role("admin"))])
async def create_user(...): ...

# 2. Gate the route AND use the caller:
@router.get("/exams/{exam_id}")
async def get_exam(exam_id: int,
                   current_user: User = Depends(require_role("admin"))):
    ...  # current_user.id / .email / .role

# 3. Any authenticated user, no role check:
async def my_exams(current_user: User = Depends(get_current_user)): ...
```

- `require_role("...")` must be **called** (it is a factory);
  `Depends(require_role)` without the argument is a bug.
- Roles are exactly `"admin"` and `"user"` (`ck_user_role` CHECK constraint).
- Both return the **SQLAlchemy `User` ORM model**, not the domain entity.
  It is loaded through the same request-scoped `get_session` (FastAPI caches
  that dependency per request), so the object is live in your router's
  session — `current_user.id` is safe to use directly in further queries.
- Status codes: **401** unauthenticated (missing/garbage/expired/forged
  token, or the user row is gone), **403** authenticated but wrong role.

## Decisions Made

- **`create_token_pair(user_id, role)` takes `role`**, though 003.md writes
  `create_token_pair(user_id)`. The access-token payload needs the role and
  the login route has already loaded the user; re-querying inside the service
  would be a wasted round trip. `rotate()` *does* load the user itself,
  because the role may have changed since the token was issued.
- **Refresh token is opaque, not a JWT.** 003.md says "JWT ngẫu nhiên"; a
  random opaque string is strictly better — it carries no claims to forge or
  leak, and its only meaning comes from the DB row.
- **`require_role` checks `current_user.role` from the DB, not the `role`
  claim in the JWT**, so a demotion takes effect immediately instead of
  waiting out the 24h access-token lifetime.
- **`HTTPBearer(auto_error=False)`** so a missing `Authorization` header
  yields our 401 + `WWW-Authenticate: Bearer` rather than FastAPI's 403.
- **`sub` is `str(user_id)`** per RFC 7519. `get_current_user` does
  `int(payload["sub"])` and 401s on anything non-numeric.
- **`_revoke_family` uses `synchronize_session="fetch"`** so rows already in
  the session's identity map reflect the bulk UPDATE.
- Login uses one identical error message for "no such email" and "wrong
  password" (no account enumeration).
- No new dependency added. `email` in `LoginRequest` is a plain `str`, not
  `EmailStr` — pydantic's `EmailStr` needs `email-validator`, which is not in
  `requirements.txt`. Add the package before using `EmailStr` anywhere.

## Files Changed

Created:
- `app/core/security.py`
- `app/application/ports/token_service.py`
- `app/infrastructure/auth/jwt_service.py`
- `app/api/dependencies.py`
- `app/api/v1/schemas/auth.py`
- `app/api/v1/routers/auth.py`
- `tests/unit/test_security.py`
- `tests/integration/test_auth_rotation.py`

Modified:
- `app/main.py` (router wiring only — the single T001 file touched)
- `.sdd/epics/exam-builder-base/003.md` (frontmatter: status closed)

## Warnings for Next Task

- **Nothing was executed.** Still no Python and no Docker in this
  environment. `pytest`, `alembic upgrade head` and even a plain `import app`
  have never run in T001/T002/T003. The first task that gets a real
  environment must run the T002 checklist *and* `pytest tests/` before
  building on any of this, and fix failures in place as defects.
- **The commit on the `RotationError` path is load-bearing.** `get_session`
  never commits, so `/auth/refresh` calls `await session.commit()` **inside
  its `except RotationError` block** before raising the 401 — otherwise the
  family revocation is rolled back when the request ends and reuse detection
  becomes a no-op. If you refactor `/auth/refresh` into a use case, keep that
  commit. Anywhere else, commit once at the end of the happy path.
- **Concurrency gap (accepted for v1):** two simultaneous `/auth/refresh`
  calls with the same valid token can both pass the `revoked` check before
  either writes. Closing it needs `SELECT ... FOR UPDATE` on the row (or
  `REPEATABLE READ`). Not required by FR-1/NFR-1; raise it if the epic ever
  grows a concurrency requirement.
- **Access tokens cannot be revoked before `exp` (24h).** Revoking a refresh
  family logs the session out of *refresh*, but an already-issued access
  token keeps working until it expires. That is the AD-2 trade-off; do not
  assume `require_role` reflects a just-revoked session. (It *does* reflect a
  just-changed role, because the role is read from the DB.)
- **Expired refresh rows are never cleaned up.** There is no reaper job and
  no `created_at` column. The table grows one row per login + one per
  refresh. Add a periodic `DELETE FROM refresh_token WHERE expires_at < now()`
  if it ever matters.
- **`tests/conftest.py` hard-codes `JWT_SECRET_KEY=test-secret-key`** via
  `os.environ.setdefault`, and `tests/integration/test_auth_rotation.py`
  repeats that literal to decode tokens. If you change the fixture value,
  change both.
- Test fixtures override `get_session` with `lambda: session` so the routers
  commit into the per-test session and assertions can read them back. Call
  `session.expire_all()` before a post-request DB assertion, otherwise you
  may be reading the identity map instead of the database. Reuse the
  `_client_for()` helper in `test_auth_rotation.py` for your own routers.
- `bcrypt` silently truncates passwords at 72 bytes; nothing validates
  password length. T010 (`POST /users`) is the natural place to add a max
  length to the request schema.
