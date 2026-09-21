"""T020 / WARN-4 — `GET /exams/{id}/submissions` must not N+1 (FR-7).

The admin results list eager-loads `Submission.answers` (`selectinload`)
and `Submission.exam_assignment` (`joinedload`). This test measures the
real SQL statement count with a `before_cursor_execute` listener on the
engine and asserts it is **the same** for an exam with 2 submissions and
an exam with 6 — i.e. constant in N rather than 1 + N (or 1 + 2N).

Unexecuted (no Python/Docker in the authoring environment). Requires the
test database described in `tests/conftest.py`.
"""

from contextlib import contextmanager

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event

from app.api.v1.routers.auth import router as auth_router
from app.api.v1.routers.submissions import router as submissions_router
from app.core.security import hash_password
from app.infrastructure.db.models.exam import Exam, ExamAssignment, ExamQuestion
from app.infrastructure.db.models.question import Option, Question
from app.infrastructure.db.models.submission import Answer, Submission
from app.infrastructure.db.models.user import User
from app.infrastructure.db.session import get_session

SMALL = 2
LARGE = 6


@pytest_asyncio.fixture
async def client(session):
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(submissions_router)
    app.dependency_overrides[get_session] = lambda: session
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.clear()


@contextmanager
def count_statements(db_engine):
    """Count every SQL statement the engine actually sends."""
    counter = {"n": 0}

    def _on_execute(conn, cursor, statement, parameters, context, executemany):
        counter["n"] += 1

    event.listen(db_engine.sync_engine, "before_cursor_execute", _on_execute)
    try:
        yield counter
    finally:
        event.remove(db_engine.sync_engine, "before_cursor_execute", _on_execute)


async def _make_exam_with_submissions(session, title: str, count: int, offset: int):
    """An exam with 2 questions and `count` submitted assignments.

    `offset` keeps the generated user emails unique across exams.
    """
    questions = []
    for i in range(2):
        question = Question(text=f"{title}-Q{i}")
        question.options = [
            Option(text="right", is_correct=True),
            Option(text="wrong", is_correct=False),
        ]
        session.add(question)
        questions.append(question)
    await session.commit()

    exam = Exam(title=title)
    exam.exam_questions = [
        ExamQuestion(question_id=q.id, order=i) for i, q in enumerate(questions)
    ]
    session.add(exam)
    await session.commit()

    for n in range(count):
        user = User(
            email=f"u{offset + n}@example.com",
            password_hash=hash_password("pw"),
            role="user",
        )
        session.add(user)
        await session.commit()

        assignment = ExamAssignment(exam_id=exam.id, user_id=user.id)
        session.add(assignment)
        await session.commit()

        submission = Submission(exam_assignment_id=assignment.id, score=2)
        submission.answers = [
            Answer(
                question_id=q.id,
                selected_option_id=next(o.id for o in q.options if o.is_correct),
                is_correct=True,
            )
            for q in questions
        ]
        session.add(submission)
        await session.commit()

    return exam.id


@pytest_asyncio.fixture
async def admin_auth(session, client):
    session.add(
        User(
            email="admin@example.com",
            password_hash=hash_password("adminpw"),
            role="admin",
        )
    )
    await session.commit()
    response = await client.post(
        "/auth/login", json={"email": "admin@example.com", "password": "adminpw"}
    )
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def test_list_submissions_query_count_is_constant_in_n(
    session, client, db_engine, admin_auth
):
    small_exam = await _make_exam_with_submissions(session, "small", SMALL, offset=0)
    large_exam = await _make_exam_with_submissions(
        session, "large", LARGE, offset=100
    )

    # Warm-up: the first request of the run also settles the authenticated
    # user in the session's identity map, which would otherwise cost the
    # small exam one extra SELECT and skew the comparison.
    warmup = await client.get(f"/exams/{small_exam}/submissions", headers=admin_auth)
    assert warmup.status_code == 200

    with count_statements(db_engine) as small_counter:
        small_response = await client.get(
            f"/exams/{small_exam}/submissions", headers=admin_auth
        )
    with count_statements(db_engine) as large_counter:
        large_response = await client.get(
            f"/exams/{large_exam}/submissions", headers=admin_auth
        )

    assert small_response.status_code == 200
    assert large_response.status_code == 200
    assert len(small_response.json()) == SMALL
    assert len(large_response.json()) == LARGE

    # The whole point: 3x the rows, the same number of round trips.
    assert large_counter["n"] == small_counter["n"], (
        f"query count scales with N: {small_counter['n']} statements for "
        f"{SMALL} submissions vs {large_counter['n']} for {LARGE}"
    )
    # And that constant is small — one SELECT for the submissions (with the
    # assignment joined in) plus one `selectinload` for all the answers.
    assert large_counter["n"] <= 3


async def test_list_submissions_returns_owner_and_breakdown(
    session, client, admin_auth
):
    exam_id = await _make_exam_with_submissions(session, "exam", SMALL, offset=0)

    response = await client.get(f"/exams/{exam_id}/submissions", headers=admin_auth)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == SMALL
    for row in body:
        assert row["user_id"] is not None
        assert row["score"] == 2
        assert row["total_questions"] == 2
        assert len(row["answers"]) == 2
        assert all(a["is_correct"] for a in row["answers"])


async def test_list_submissions_is_admin_only(session, client):
    exam_id = await _make_exam_with_submissions(session, "exam", SMALL, offset=0)
    response = await client.post(
        "/auth/login", json={"email": "u0@example.com", "password": "pw"}
    )
    learner_auth = {"Authorization": f"Bearer {response.json()['access_token']}"}

    forbidden = await client.get(
        f"/exams/{exam_id}/submissions", headers=learner_auth
    )

    assert forbidden.status_code == 403
    assert "score" not in forbidden.text
