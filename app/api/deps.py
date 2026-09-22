"""Shared FastAPI dependencies: authentication and role authorization.

Every protected router in this epic depends on these two symbols::

    from app.api.deps import get_current_user, require_role

    @router.post("/users", dependencies=[Depends(require_role("admin"))])
    ...
    # or, when the handler needs the caller:
    async def handler(current_user: User = Depends(require_role("admin"))): ...

`get_current_user` returns the **SQLAlchemy `User` model** (not the domain
entity) loaded through the *same* request-scoped session the router gets
from `get_session` — FastAPI caches `Depends(get_session)` per request — so
the returned object is live in that session and usable in further queries.
"""

from collections.abc import Awaitable, Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt_service import JWTError, decode_access_token
from app.models.user import User
from app.core.database import get_session

# auto_error=False so a missing header produces our own 401 with a
# `WWW-Authenticate` header rather than FastAPI's bare 403.
_bearer_scheme = HTTPBearer(auto_error=False)


def _unauthorized() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    if credentials is None or not credentials.credentials:
        raise _unauthorized()

    try:
        payload = decode_access_token(credentials.credentials)
    except JWTError:
        raise _unauthorized()

    try:
        user_id = int(payload.get("sub"))
    except (TypeError, ValueError):
        raise _unauthorized()

    user = await session.get(User, user_id)
    if user is None:
        raise _unauthorized()
    return user


def require_role(role: str) -> Callable[..., Awaitable[User]]:
    async def _require_role(
        current_user: User = Depends(get_current_user),
    ) -> User:
        if current_user.role != role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user

    return _require_role
