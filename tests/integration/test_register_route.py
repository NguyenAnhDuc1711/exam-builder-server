"""`POST /auth/register` — public self-service sign-up.

Follows the same ASGI-through-httpx pattern as `test_auth_rotation.py`, with
`get_session` overridden to the per-test `session` fixture.
"""

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy import select

from app.auth.jwt_service import JWT_ALGORITHM
from app.core.database import get_session
from app.core.security import hash_password
from app.main import app as main_app
from app.models.user import User

JWT_SECRET_KEY = "test-secret-key"  # matches tests/conftest.py


def _client_for(fastapi_app: FastAPI, session) -> AsyncClient:
    fastapi_app.dependency_overrides[get_session] = lambda: session
    return AsyncClient(
        transport=ASGITransport(app=fastapi_app), base_url="http://test"
    )


@pytest_asyncio.fixture
async def client(session):
    async with _client_for(main_app, session) as c:
        yield c
    main_app.dependency_overrides.clear()


async def _register(client, email: str, password: str):
    return await client.post(
        "/auth/register", json={"email": email, "password": password}
    )


async def test_register_creates_user_and_returns_token_pair(session, client):
    response = await _register(client, "newuser@example.com", "s3cret1")

    assert response.status_code == 201
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["refresh_token"]

    payload = jwt.decode(
        body["access_token"], JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM]
    )
    assert payload["role"] == "user"

    session.expire_all()
    row = (
        await session.execute(select(User).where(User.email == "newuser@example.com"))
    ).scalar_one()
    assert row.role == "user"
    assert row.password_hash != "s3cret1"


async def test_register_cannot_set_role(session, client):
    response = await client.post(
        "/auth/register",
        json={"email": "wannabe-admin@example.com", "password": "s3cret1", "role": "admin"},
    )

    assert response.status_code == 201
    payload = jwt.decode(
        response.json()["access_token"], JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM]
    )
    assert payload["role"] == "user"


async def test_register_duplicate_email_returns_409(session, client):
    session.add(
        User(
            email="taken@example.com",
            password_hash=hash_password("whatever"),
            role="user",
        )
    )
    await session.commit()

    response = await _register(client, "taken@example.com", "s3cret1")

    assert response.status_code == 409
