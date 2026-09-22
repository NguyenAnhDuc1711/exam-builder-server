"""Request/response models for `/auth`."""

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=72)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(max_length=512)


class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
