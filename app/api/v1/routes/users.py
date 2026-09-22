"""`/users` — admin-only account creation (FR-2).

There is no public sign-up route anywhere in the API; `POST /users` is the
only way a `user` account is created, and only an admin may call it.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.schemas.users import CreateUserRequest, UserResponse
from app.services.create_user import (
    EmailAlreadyExistsError,
    create_user,
)
from app.models.user import User
from app.core.database import get_session

router = APIRouter()


@router.post(
    "",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_role("admin"))],
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
