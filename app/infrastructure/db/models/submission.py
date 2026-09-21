"""`submission` / `answer` tables.

`submission.exam_assignment_id` is UNIQUE — this is the DB-level guarantee
behind FR-6's single-attempt rule: a second submission for the same
assignment raises `IntegrityError`.
"""

import sqlalchemy as sa
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.db.base import Base


class Submission(Base):
    __tablename__ = "submission"
    __table_args__ = (
        UniqueConstraint(
            "exam_assignment_id", name="uq_submission_exam_assignment_id"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    exam_assignment_id: Mapped[int] = mapped_column(
        ForeignKey("exam_assignment.id", ondelete="CASCADE"), nullable=False
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=sa.func.now()
    )
    # Filled in by the grading step of the same transaction as the insert
    # (AD-4, synchronous grading); defaults to 0 so it is never NULL.
    score: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=sa.text("0")
    )

    exam_assignment: Mapped["ExamAssignment"] = relationship()  # noqa: F821
    answers: Mapped[list["Answer"]] = relationship(
        back_populates="submission",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Answer(Base):
    __tablename__ = "answer"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("submission.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id: Mapped[int] = mapped_column(
        ForeignKey("question.id"), nullable=False
    )
    # NULL = the question was left unanswered; such an answer is never correct.
    selected_option_id: Mapped[int | None] = mapped_column(
        ForeignKey("option.id"), nullable=True
    )
    is_correct: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa.false()
    )

    submission: Mapped["Submission"] = relationship(back_populates="answers")
