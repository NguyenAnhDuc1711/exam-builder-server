"""Request/response models for `/users`."""

from typing import Literal

from pydantic import BaseModel, EmailStr, Field

Role = Literal["admin", "user"]


class CreateUserRequest(BaseModel):
    email: EmailStr = Field(max_length=255)
    password: str = Field(max_length=72)


class UserResponse(BaseModel):
    id: int
    email: str
    role: Role

    model_config = {"from_attributes": True}
