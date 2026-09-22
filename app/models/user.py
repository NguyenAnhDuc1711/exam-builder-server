"""`user` table — SQLAlchemy 2.0 ORM model.

NFR-3: single-tenant. There is deliberately no `organization_id` column
here or anywhere else in the schema.

Note: `user` is a reserved word in PostgreSQL. SQLAlchemy/Alembic quote it
automatically; any hand-written SQL must spell it `"user"`.
"""

from sqlalchemy import CheckConstraint, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class User(Base):
    __tablename__ = "user"
    __table_args__ = (
        CheckConstraint("role IN ('admin', 'user')", name="ck_user_role"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
