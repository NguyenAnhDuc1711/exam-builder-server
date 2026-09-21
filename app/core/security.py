"""Password hashing and opaque-token hashing.

Two *deliberately different* primitives (R-6):

* `hash_password` / `verify_password` use **bcrypt** — slow by design, so a
  leaked `user.password_hash` is expensive to brute-force. Passwords are
  low-entropy human input, so the cost factor is the whole point.
* `hash_token` uses **SHA-256** — fast, deterministic, unsalted, so a
  refresh token can be looked up by an indexed equality match. That is safe
  only because refresh tokens are 256+ bits of `secrets`-grade entropy:
  there is nothing to brute-force. Never use this for passwords, and never
  use bcrypt for refresh tokens (a salted hash cannot be looked up).
"""

import hashlib

from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Return a bcrypt hash (salt included) suitable for `user.password_hash`."""
    return _pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Constant-time-ish bcrypt verification; never raises on a bad hash."""
    try:
        return _pwd_context.verify(password, password_hash)
    except ValueError:
        # Malformed/legacy hash in the DB — treat as "does not match" rather
        # than leaking a 500 to the caller.
        return False


def hash_token(token: str) -> str:
    """SHA-256 hex digest of an opaque token — exactly 64 chars.

    Matches `refresh_token.token_hash` (`String(64)`).
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
