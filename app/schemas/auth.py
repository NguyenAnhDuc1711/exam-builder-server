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


class ForgotPasswordRequest(BaseModel):
    email: EmailStr = Field(max_length=255)


class VerifyOtpRequest(BaseModel):
    email: EmailStr = Field(max_length=255)
    code: str = Field(min_length=6, max_length=6)


class VerifyOtpResponse(BaseModel):
    reset_token: str


class ResetPasswordRequest(BaseModel):
    reset_token: str = Field(max_length=512)
    new_password: str = Field(max_length=72)


class MessageResponse(BaseModel):
    message: str

