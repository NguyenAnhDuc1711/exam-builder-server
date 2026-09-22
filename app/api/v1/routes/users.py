"""`/users` — admin-only account creation (FR-2).

`POST /users` lets an admin provision a `user` account directly. Public
self-service sign-up is also available via `POST /auth/register`
(`app/api/v1/routes/auth.py`); both routes share `create_user` and always
create `role="user"` accounts.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.api.rate_limit import rate_limit
from app.schemas.users import CreateUserRequest, UserResponse
from app.services.create_user import (
    EmailAlreadyExistsError,
    create_user,
)
from app.models.user import User
from app.core.database import get_session

router = APIRouter(prefix="/users", tags=["users"])


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role("admin")), Depends(rate_limit("write"))],
)
async def create_user_route(
    body: CreateUserRequest,
    session: AsyncSession = Depends(get_session),
) -> User:
    try:
        return await create_user(session, body.email, body.password)
    except EmailAlreadyExistsError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )
