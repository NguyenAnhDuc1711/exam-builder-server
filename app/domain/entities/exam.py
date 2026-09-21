"""Exam / ExamAssignment domain entities.

Pure Python — no SQLAlchemy imports (AD-1).
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Exam:
    id: int | None
    title: str
    # Ordered: index in this list is the question's position in the exam,
    # persisted as `exam_question.order`.
    question_ids: list[int] = field(default_factory=list)


@dataclass
class ExamAssignment:
    id: int | None
    exam_id: int
    user_id: int
    assigned_at: datetime | None = None
