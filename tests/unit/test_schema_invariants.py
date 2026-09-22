"""Schema invariants that need no database.

NOTE (T002): written without a Python runtime available in the authoring
environment — unexecuted, see the T002 handoff.
"""

import app.models  # noqa: F401  (registers tables)
from app.models.base import Base

EXPECTED_TABLES = {
    "user",
    "question",
    "option",
    "exam",
    "exam_question",
    "exam_assignment",
    "submission",
    "answer",
    "refresh_token",
}


def test_all_nine_tables_are_defined():
    assert set(Base.metadata.tables) == EXPECTED_TABLES


def test_no_multi_tenant_columns_anywhere():
    """NFR-3: single-tenant — no `organization_id` / tenant concept."""
    for table in Base.metadata.tables.values():
        for column in table.columns:
            name = column.name.lower()
            assert "organization" not in name, f"{table.name}.{column.name}"
            assert "tenant" not in name, f"{table.name}.{column.name}"


def test_submission_enforces_single_attempt():
    constraint_columns = {
        tuple(c.name for c in uq.columns)
        for uq in Base.metadata.tables["submission"].constraints
        if hasattr(uq, "columns") and uq.__class__.__name__ == "UniqueConstraint"
    }
    assert ("exam_assignment_id",) in constraint_columns


def test_exam_assignment_is_unique_per_exam_and_user():
    constraint_columns = {
        tuple(c.name for c in uq.columns)
        for uq in Base.metadata.tables["exam_assignment"].constraints
        if hasattr(uq, "columns") and uq.__class__.__name__ == "UniqueConstraint"
    }
    assert ("exam_id", "user_id") in constraint_columns


def test_user_password_changed_at_column_is_timezone_aware():
    from datetime import datetime, timezone
    from app.models.user import User

    col = Base.metadata.tables["user"].columns["password_changed_at"]
    assert col.nullable is True
    assert col.type.timezone is True

    user = User(email="test@example.com", password_hash="hash", role="user")
    assert user.password_changed_at is None
    now = datetime.now(timezone.utc)
    user.password_changed_at = now
    assert user.password_changed_at.tzinfo is not None

