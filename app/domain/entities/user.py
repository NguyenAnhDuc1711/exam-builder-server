"""User domain entity.

Pure Python — no SQLAlchemy, no Pydantic, no framework imports (AD-1).
"""

from dataclasses import dataclass
from typing import Literal

Role = Literal["admin", "user"]


@dataclass
class User:
    id: int | None
    email: str
    password_hash: str
    role: Role
