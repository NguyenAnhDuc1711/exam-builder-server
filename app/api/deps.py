from collections.abc import Awaitable, Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.jwt_service import JWTError, decode_access_token
from app.models.user import User
from app.core.database import get_session

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

    # Token invalidation post-reset (AD-3, FR-7)
    if user.password_changed_at is not None:
        iat = payload.get("iat")
        if not isinstance(iat, (int, float)):
            raise _unauthorized()
        pwd_changed_epoch = int(user.password_changed_at.timestamp()) - 1
        if int(iat) < pwd_changed_epoch:
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
