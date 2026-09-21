"""T010 — `POST /users`: admin-only account creation (FR-2).

Unexecuted (no Python/Docker in the authoring environment). Requires the
test database described in `tests/conftest.py`. Follows the same
ASGI-through-httpx pattern as `tests/integration/test_auth_rotation.py`,
with `get_session` overridden to the per-test `session` fixture.
"""

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.api.v1.routers.auth import router as auth_router
from app.api.v1.routers.users import router as users_router
from app.core.security import hash_password
from app.infrastructure.db.models.user import User
from app.infrastructure.db.session import get_session


def _client_for(fastapi_app: FastAPI, session) -> AsyncClient:
    fastapi_app.dependency_overrides[get_session] = lambda: session
    return AsyncClient(
        transport=ASGITransport(app=fastapi_app), base_url="http://test"
    )


@pytest_asyncio.fixture
async def client(session):
    """A throwaway app exposing `/auth` (to log in) and `/users` (under test)."""
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(users_router)
    async with _client_for(app, session) as c:
        yield c
    app.dependency_overrides.clear()


async def _make_user(session, email: str, password: str, role: str) -> User:
    user = User(email=email, password_hash=hash_password(password), role=role)
    session.add(user)
    await session.commit()
    return user


async def _access_token(client, email: str, password: str) -> str:
    response = await client.post(
        "/auth/login", json={"email": email, "password": password}
    )
    return response.json()["access_token"]


async def _create_user(client, token: str, email: str, password: str):
    return await client.post(
        "/users",
        json={"email": email, "password": password},
        headers={"Authorization": f"Bearer {token}"},
    )


# ------------------------------------------------------------------- success


async def test_admin_creates_user_returns_201_without_password_hash(
    session, client
):
    await _make_user(session, "admin@example.com", "adminpw", "admin")
    token = await _access_token(client, "admin@example.com", "adminpw")

    response = await _create_user(client, token, "newuser@example.com", "s3cret1")

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "newuser@example.com"
    assert body["role"] == "user"
    assert "password_hash" not in body
    assert "password" not in body

    session.expire_all()
    row = (
        await session.execute(
            select(User).where(User.email == "newuser@example.com")
        )
    ).scalar_one()
    assert row.role == "user"
    assert row.password_hash != "s3cret1"


# ------------------------------------------------------------------ non-admin


async def test_non_admin_creating_user_returns_403(session, client):
    await _make_user(session, "user@example.com", "userpw", "user")
    token = await _access_token(client, "user@example.com", "userpw")

    response = await _create_user(client, token, "newuser@example.com", "s3cret1")

    assert response.status_code == 403


# ---------------------------------------------------------------- no token


async def test_creating_user_without_token_returns_401(client):
    response = await client.post(
        "/users", json={"email": "newuser@example.com", "password": "s3cret1"}
    )

    assert response.status_code == 401


# ----------------------------------------------------------------- duplicate


async def test_duplicate_email_returns_409(session, client):
    await _make_user(session, "admin@example.com", "adminpw", "admin")
    await _make_user(session, "taken@example.com", "whatever", "user")
    token = await _access_token(client, "admin@example.com", "adminpw")

    response = await _create_user(client, token, "taken@example.com", "s3cret1")

    assert response.status_code == 409
