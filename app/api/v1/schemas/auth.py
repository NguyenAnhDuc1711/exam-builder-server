"""Request/response models for `/auth`.

`email` is a plain `str`, not `EmailStr`: pydantic's email validation needs
the `email-validator` package, which is not in `requirements.txt`.
"""

from pydantic import BaseModel


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPairResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
