"""`/users` — admin-only account creation (FR-2).

There is no public sign-up route anywhere in the API; `POST /users` is the
only way a `user` account is created, and only an admin may call it.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import require_role
from app.application.use_cases.create_user import (
    EmailAlreadyExistsError,
    create_user,
)
from app.infrastructure.db.models.user import User
from app.infrastructure.db.session import get_session

router = APIRouter(prefix="/users", tags=["users"])


class CreateUserRequest(BaseModel):
    # Plain `str`, not `EmailStr`: `email-validator` is not a dependency
    # (same choice as `app/api/v1/schemas/auth.py`).
    email: str
    # bcrypt silently truncates beyond 72 bytes (app/core/security.py); reject
    # an over-long password up front instead of accepting one whose tail is
    # silently discarded.
    password: str = Field(max_length=72)
    # No `role` field: this endpoint always creates `role="user"` accounts
    # (010.md — admins cannot mint other admins here in v1).


class UserResponse(BaseModel):
    id: int
    email: str
    role: str

    model_config = {"from_attributes": True}


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
