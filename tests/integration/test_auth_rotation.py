"""T003 — login, refresh rotation, reuse detection, role gating.

Unexecuted (no Python/Docker in the authoring environment). Requires the
test database described in `tests/conftest.py`.

Every test drives the real ASGI app through httpx, with `get_session`
overridden to the per-test `session` fixture so the assertions can read the
same transaction the routers committed.
"""

import hashlib

import pytest
import pytest_asyncio
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy import select

from app.api.dependencies import require_role
from app.api.v1.routers.auth import router as auth_router
from app.core.security import hash_password
from app.infrastructure.auth.jwt_service import JWT_ALGORITHM
from app.infrastructure.db.models.refresh_token import RefreshToken
from app.infrastructure.db.models.user import User
from app.infrastructure.db.session import get_session
from app.main import app as main_app

JWT_SECRET_KEY = "test-secret-key"  # matches tests/conftest.py


async def _make_user(session, email: str, password: str, role: str) -> User:
    user = User(email=email, password_hash=hash_password(password), role=role)
    session.add(user)
    await session.commit()
    return user


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


@pytest_asyncio.fixture
async def guarded_client(session):
    """A throwaway app exposing an admin-only route, to exercise require_role."""
    guarded = FastAPI()
    guarded.include_router(auth_router)

    @guarded.get("/admin-only")
    async def admin_only(current_user: User = Depends(require_role("admin"))):
        return {"email": current_user.email}

    async with _client_for(guarded, session) as c:
        yield c
    guarded.dependency_overrides.clear()


async def _login(client, email: str, password: str):
    return await client.post(
        "/auth/login", json={"email": email, "password": password}
    )


async def _refresh(client, refresh_token: str):
    return await client.post(
        "/auth/refresh", json={"refresh_token": refresh_token}
    )


# --------------------------------------------------------------------- login


async def test_login_success_returns_valid_token_pair(session, client):
    user = await _make_user(session, "admin@example.com", "s3cret", "admin")

    response = await _login(client, "admin@example.com", "s3cret")

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["refresh_token"]

    payload = jwt.decode(
        body["access_token"], JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM]
    )
    assert payload["sub"] == str(user.id)
    assert payload["role"] == "admin"
    # exp ~= now + 24h (JWT_ACCESS_EXPIRE_MINUTES=1440).
    assert payload["exp"] - payload["iat"] == 1440 * 60


async def test_login_with_wrong_password_returns_401(session, client):
    await _make_user(session, "user@example.com", "correct", "user")

    response = await _login(client, "user@example.com", "wrong")

    assert response.status_code == 401


async def test_login_with_unknown_email_returns_401(client):
    response = await _login(client, "nobody@example.com", "whatever")
    assert response.status_code == 401


# ------------------------------------------------------------------- refresh


async def test_refresh_rotates_and_invalidates_the_old_token(session, client):
    await _make_user(session, "user@example.com", "pw", "user")
    rt0 = (await _login(client, "user@example.com", "pw")).json()["refresh_token"]

    first = await _refresh(client, rt0)
    assert first.status_code == 200
    rt1 = first.json()["refresh_token"]
    assert rt1 != rt0

    # Second use of the *same* old token must fail.
    second = await _refresh(client, rt0)
    assert second.status_code == 401


async def test_refresh_with_unknown_token_returns_401(client):
    assert (await _refresh(client, "not-a-real-token")).status_code == 401


# ----------------------------------------------------- NFR-1: reuse detection


async def test_reuse_revokes_the_entire_family_including_unused_tokens(
    session, client
):
    """The whole point of family_id: burning a leaked chain end to end."""
    await _make_user(session, "victim@example.com", "pw", "user")
    rt0 = (await _login(client, "victim@example.com", "pw")).json()["refresh_token"]

    # Legitimate rotation: rt0 -> rt1. rt1 has never been used.
    rt1 = (await _refresh(client, rt0)).json()["refresh_token"]

    # Attacker replays the already-rotated rt0.
    assert (await _refresh(client, rt0)).status_code == 401

    # rt1 was perfectly valid a moment ago and was never used — reuse
    # detection must have revoked it too.
    assert (await _refresh(client, rt1)).status_code == 401

    session.expire_all()  # force a real DB read, not the identity map
    rows = (await session.execute(select(RefreshToken))).scalars().all()
    assert len(rows) == 2
    assert len({row.family_id for row in rows}) == 1  # both in one family
    assert all(row.revoked for row in rows)


async def test_a_second_login_starts_an_independent_family(session, client):
    """Burning one family must not log the user out of their other sessions."""
    await _make_user(session, "user@example.com", "pw", "user")
    family_a = (await _login(client, "user@example.com", "pw")).json()[
        "refresh_token"
    ]
    family_b = (await _login(client, "user@example.com", "pw")).json()[
        "refresh_token"
    ]

    await _refresh(client, family_a)  # rotate family A
    assert (await _refresh(client, family_a)).status_code == 401  # burn family A

    # Family B is untouched.
    assert (await _refresh(client, family_b)).status_code == 200


# ------------------------------------------------------- R-6: no plaintext


async def test_refresh_tokens_are_never_stored_in_plaintext(session, client):
    await _make_user(session, "user@example.com", "pw", "user")
    rt0 = (await _login(client, "user@example.com", "pw")).json()["refresh_token"]
    rt1 = (await _refresh(client, rt0)).json()["refresh_token"]

    session.expire_all()
    hashes = (
        (await session.execute(select(RefreshToken.token_hash))).scalars().all()
    )

    assert len(hashes) == 2
    for stored in hashes:
        assert len(stored) == 64
        assert stored not in (rt0, rt1)
    assert hashlib.sha256(rt0.encode()).hexdigest() in hashes
    assert hashlib.sha256(rt1.encode()).hexdigest() in hashes


# ---------------------------------------------------------------- require_role


async def test_require_role_blocks_a_non_admin_with_403(session, guarded_client):
    await _make_user(session, "user@example.com", "pw", "user")
    access = (await _login(guarded_client, "user@example.com", "pw")).json()[
        "access_token"
    ]

    response = await guarded_client.get(
        "/admin-only", headers={"Authorization": f"Bearer {access}"}
    )

    assert response.status_code == 403


async def test_require_role_allows_the_matching_role(session, guarded_client):
    await _make_user(session, "admin@example.com", "pw", "admin")
    access = (await _login(guarded_client, "admin@example.com", "pw")).json()[
        "access_token"
    ]

    response = await guarded_client.get(
        "/admin-only", headers={"Authorization": f"Bearer {access}"}
    )

    assert response.status_code == 200
    assert response.json() == {"email": "admin@example.com"}


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer garbage"}, {"Authorization": "Basic abc"}],
)
async def test_protected_route_requires_a_valid_bearer_token(
    guarded_client, headers
):
    response = await guarded_client.get("/admin-only", headers=headers)
    assert response.status_code == 401
