"""`refresh_token` table (AD-2).

R-6: `token_hash` stores the SHA-256 **hex digest** of the refresh token,
never the plaintext token. `family_id` groups every token issued from one
login so that reuse of an already-revoked token can revoke the whole family.
"""

import sqlalchemy as sa
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class RefreshToken(Base):
    __tablename__ = "refresh_token"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # SHA-256 hex digest — exactly 64 characters.
    token_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    # UUID4 string (36 chars) shared by every token in one rotation chain.
    family_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    revoked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa.false()
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
