"""Application-layer port for issuing and rotating auth tokens (AD-2).

The application layer knows *that* tokens are issued and rotated; it does
not know they are JWTs, nor that refresh-token hashes live in a table. The
concrete implementation is `app.infrastructure.auth.jwt_service`.
"""

from abc import ABC, abstractmethod
from typing import NamedTuple


class TokenPair(NamedTuple):
    """An access token (short-lived, self-contained) + its refresh token."""

    access_token: str
    refresh_token: str


class RotationError(Exception):
    """A refresh token could not be rotated.

    Raised for an unknown token, an expired token, and — critically — for a
    token that has already been rotated (reuse detection). The API layer maps
    every case to a plain `401` and deliberately does **not** tell the caller
    which one it was.
    """


class TokenServicePort(ABC):
    @abstractmethod
    async def create_token_pair(self, user_id: int, role: str) -> TokenPair:
        """Start a new token family for `user_id` (i.e. a fresh login)."""

    @abstractmethod
    async def rotate(self, refresh_token: str) -> TokenPair:
        """Exchange `refresh_token` for a new pair in the same family.

        Raises `RotationError` if the token is not usable. Implementations
        must revoke the whole family on reuse.
        """
