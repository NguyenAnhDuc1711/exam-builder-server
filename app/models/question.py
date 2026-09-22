import sqlalchemy as sa
from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Question(Base):
    __tablename__ = "question"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    image_url: Mapped[str | None] = mapped_column(String(512), nullable=True)

    options: Mapped[list["Option"]] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Option(Base):
    __tablename__ = "option"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    question_id: Mapped[int] = mapped_column(
        ForeignKey("question.id", ondelete="CASCADE"), nullable=False, index=True
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    is_correct: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa.false()
    )

    question: Mapped["Question"] = relationship(back_populates="options")
