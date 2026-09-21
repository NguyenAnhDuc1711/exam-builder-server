"""T012 — `POST /exams`: exam assembly from question bank ids (FR-4, WARN-1).

Unexecuted (no Python/Docker in the authoring environment). Requires the
test database described in `tests/conftest.py`. Same ASGI-through-httpx
pattern as `tests/integration/test_admin_users.py`, with `get_session`
overridden to the per-test `session` fixture. Questions are inserted
directly via the `session` fixture (not through `POST /questions`) since
assembly only cares about `Question.id` existing, not option content.
"""

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.api.v1.routers.auth import router as auth_router
from app.api.v1.routers.exams import router as exams_router
from app.core.security import hash_password
from app.infrastructure.db.models.exam import Exam, ExamQuestion
from app.infrastructure.db.models.question import Question
from app.infrastructure.db.models.user import User
from app.infrastructure.db.session import get_session


@pytest_asyncio.fixture
async def client(session):
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(exams_router)
    app.dependency_overrides[get_session] = lambda: session
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c
    app.dependency_overrides.clear()


async def _make_admin(session) -> None:
    session.add(
        User(
            email="admin@example.com",
            password_hash=hash_password("adminpw"),
            role="admin",
        )
    )
    await session.commit()


async def _admin_token(client) -> str:
    response = await client.post(
        "/auth/login", json={"email": "admin@example.com", "password": "adminpw"}
    )
    return response.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _make_questions(session, count: int) -> list[int]:
    questions = [Question(text=f"Q{i}") for i in range(count)]
    session.add_all(questions)
    await session.commit()
    return [q.id for q in questions]


# ------------------------------------------------------------------- success


async def test_assemble_exam_with_valid_question_ids_preserves_order(
    session, client
):
    await _make_admin(session)
    token = await _admin_token(client)
    ids = await _make_questions(session, 3)
    # Deliberately not in id order, to prove request order is honored
    # rather than, say, sorted question ids.
    ordered_ids = [ids[2], ids[0], ids[1]]

    response = await client.post(
        "/exams",
        json={"title": "Midterm", "question_ids": ordered_ids},
        headers=_auth(token),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Midterm"
    returned_ids = [eq["question_id"] for eq in body["exam_questions"]]
    assert returned_ids == ordered_ids

    session.expire_all()
    rows = (
        (
            await session.execute(
                select(ExamQuestion)
                .where(ExamQuestion.exam_id == body["id"])
                .order_by(ExamQuestion.order)
            )
        )
        .scalars()
        .all()
    )
    assert [r.question_id for r in rows] == ordered_ids


# -------------------------------------------------------------------- WARN-1


async def test_assemble_exam_with_missing_question_id_returns_404_no_partial_insert(
    session, client
):
    await _make_admin(session)
    token = await _admin_token(client)
    ids = await _make_questions(session, 2)
    missing_id = max(ids) + 1000

    response = await client.post(
        "/exams",
        json={"title": "Broken exam", "question_ids": [ids[0], missing_id, ids[1]]},
        headers=_auth(token),
    )

    assert response.status_code == 404
    assert missing_id in response.json()["detail"]["missing_ids"]

    session.expire_all()
    exams = (await session.execute(select(Exam))).scalars().all()
    exam_questions = (await session.execute(select(ExamQuestion))).scalars().all()
    assert exams == []
    assert exam_questions == []
