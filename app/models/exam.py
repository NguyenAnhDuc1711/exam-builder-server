import sqlalchemy as sa
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Exam(Base):
    __tablename__ = "exam"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)

    exam_questions: Mapped[list["ExamQuestion"]] = relationship(
        back_populates="exam",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ExamQuestion.order",
    )


class ExamQuestion(Base):
    __tablename__ = "exam_question"

    exam_id: Mapped[int] = mapped_column(
        ForeignKey("exam.id", ondelete="CASCADE"), primary_key=True
    )
    question_id: Mapped[int] = mapped_column(
        ForeignKey("question.id", ondelete="CASCADE"), primary_key=True
    )
    order: Mapped[int] = mapped_column(Integer, nullable=False)

    exam: Mapped["Exam"] = relationship(back_populates="exam_questions")
    question: Mapped["Question"] = relationship()  # noqa: F821


class ExamAssignment(Base):
    __tablename__ = "exam_assignment"
    __table_args__ = (
        UniqueConstraint(
            "exam_id", "user_id", name="uq_exam_assignment_exam_id_user_id"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_id: Mapped[int] = mapped_column(
        ForeignKey("exam.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("user.id", ondelete="CASCADE"), nullable=False, index=True
    )
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )

    exam: Mapped["Exam"] = relationship()
    user: Mapped["User"] = relationship()  # noqa: F821
