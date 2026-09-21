"""Submission / Answer domain entities.

Pure Python — no SQLAlchemy imports (AD-1).
"""

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Answer:
    id: int | None
    submission_id: int | None
    question_id: int
    # None = question left unanswered; such an answer is never correct.
    selected_option_id: int | None
    is_correct: bool


@dataclass
class Submission:
    id: int | None
    exam_assignment_id: int
    submitted_at: datetime | None = None
    score: int = 0
    answers: list[Answer] = field(default_factory=list)
