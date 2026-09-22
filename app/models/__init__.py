"""Importing this package registers every ORM model on `Base.metadata`.

Alembic's `env.py` and the test fixtures rely on that: a model module that
is never imported is invisible to `Base.metadata` (and therefore to
autogenerate and to `create_all`).
"""

from app.models.base import Base
from app.models.exam import Exam, ExamAssignment, ExamQuestion
from app.models.question import Option, Question
from app.models.refresh_token import RefreshToken
from app.models.submission import Answer, Submission
from app.models.user import User

__all__ = [
    "Answer",
    "Base",
    "Exam",
    "ExamAssignment",
    "ExamQuestion",
    "Option",
    "Question",
    "RefreshToken",
    "Submission",
    "User",
]
