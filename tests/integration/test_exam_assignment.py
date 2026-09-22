"""T012 — `POST /exams/{id}/assign`: exam assignment to a user (FR-5).

Unexecuted (no Python/Docker in the authoring environment). Requires the
test database described in `tests/conftest.py`. Same ASGI-through-httpx
pattern as `tests/integration/test_admin_users.py`.
"""

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.v1.routes.auth import router as auth_router
from app.api.v1.routes.exams import router as exams_router
from app.core.security import hash_password
from app.models.exam import Exam
from app.models.question import Question
from app.models.user import User
from app.core.database import get_session


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


async def _make_user(session, email: str = "learner@example.com") -> User:
    user = User(email=email, password_hash=hash_password("userpw"), role="user")
    session.add(user)
    await session.commit()
    return user


async def _admin_token(client) -> str:
    response = await client.post(
        "/auth/login", json={"email": "admin@example.com", "password": "adminpw"}
    )
    return response.json()["access_token"]


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _make_exam(session) -> int:
    question = Question(text="Q1")
    session.add(question)
    await session.commit()
    exam = Exam(title="Exam")
    session.add(exam)
    await session.commit()
    return exam.id


# ------------------------------------------------------------------- success


async def test_assign_exam_to_existing_user_returns_201(session, client):
    await _make_admin(session)
    token = await _admin_token(client)
    exam_id = await _make_exam(session)
    user = await _make_user(session)

    response = await client.post(
        f"/exams/{exam_id}/assign",
        json={"user_id": user.id},
        headers=_auth(token),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["exam_id"] == exam_id
    assert body["user_id"] == user.id


# ----------------------------------------------------------------- duplicate


async def test_duplicate_assignment_returns_409(session, client):
    await _make_admin(session)
    token = await _admin_token(client)
    exam_id = await _make_exam(session)
    user = await _make_user(session)

    first = await client.post(
        f"/exams/{exam_id}/assign", json={"user_id": user.id}, headers=_auth(token)
    )
    assert first.status_code == 201

    second = await client.post(
        f"/exams/{exam_id}/assign", json={"user_id": user.id}, headers=_auth(token)
    )
    assert second.status_code == 409


# ---------------------------------------------------------------- missing user


async def test_assign_to_nonexistent_user_returns_404(session, client):
    await _make_admin(session)
    token = await _admin_token(client)
    exam_id = await _make_exam(session)

    response = await client.post(
        f"/exams/{exam_id}/assign",
        json={"user_id": 999999},
        headers=_auth(token),
    )

    assert response.status_code == 404
