"""T011 — `/questions`: question bank CRUD + image validation (FR-3, WARN-3).

Unexecuted (no Python/Docker in the authoring environment). Same
ASGI-through-httpx pattern as `tests/integration/test_admin_users.py`, with
`get_session` overridden to the per-test `session` fixture and
`get_image_storage` overridden to an in-memory mock so no test ever makes a
real network call to Cloudinary.
"""

import json
from unittest.mock import AsyncMock

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.v1.routers.auth import router as auth_router
from app.api.v1.routers.questions import get_image_storage
from app.api.v1.routers.questions import router as questions_router
from app.application.ports.image_storage import ImageStoragePort
from app.core.security import hash_password
from app.infrastructure.db.models.user import User
from app.infrastructure.db.session import get_session

# Real magic-byte signatures — enough for our own sniffing logic, which only
# inspects the header, not a fully-valid image codestream.
_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"fake-png-body"
_PDF_BYTES = b"%PDF-1.4\nfake pdf content"
_OVERSIZED_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"x" * (5 * 1024 * 1024 + 1)


@pytest_asyncio.fixture
async def image_storage_mock():
    return AsyncMock(spec=ImageStoragePort)


@pytest_asyncio.fixture
async def client(session, image_storage_mock):
    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(questions_router)
    app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_image_storage] = lambda: image_storage_mock
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


def _options_field(options: list[dict]) -> str:
    return json.dumps(options)


# ------------------------------------------------------------- text-only


async def test_create_text_only_question_returns_201(session, client):
    await _make_admin(session)
    token = await _admin_token(client)

    response = await client.post(
        "/questions",
        data={
            "text": "What is 2+2?",
            "options": _options_field(
                [{"text": "3", "is_correct": False}, {"text": "4", "is_correct": True}]
            ),
        },
        headers=_auth(token),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["text"] == "What is 2+2?"
    assert body["image_url"] is None
    assert body.get("image_upload_warning") is None
    assert len(body["options"]) == 2


# ------------------------------------------------------------- valid image


async def test_create_question_with_valid_image_sets_image_url(
    session, client, image_storage_mock
):
    await _make_admin(session)
    token = await _admin_token(client)
    image_storage_mock.upload.return_value = "https://cloudinary.example/q.png"

    response = await client.post(
        "/questions",
        data={
            "text": "Pick the correct one",
            "options": _options_field(
                [{"text": "A", "is_correct": True}, {"text": "B", "is_correct": False}]
            ),
        },
        files={"image": ("q.png", _PNG_BYTES, "image/png")},
        headers=_auth(token),
    )

    assert response.status_code == 201
    body = response.json()
    assert body["image_url"] == "https://cloudinary.example/q.png"
    assert body.get("image_upload_warning") is None
    image_storage_mock.upload.assert_called_once()


# ------------------------------------------------------------- bad options count


async def test_zero_correct_options_returns_400(session, client):
    await _make_admin(session)
    token = await _admin_token(client)

    response = await client.post(
        "/questions",
        data={
            "text": "Broken question",
            "options": _options_field(
                [{"text": "A", "is_correct": False}, {"text": "B", "is_correct": False}]
            ),
        },
        headers=_auth(token),
    )

    assert response.status_code == 400


async def test_multiple_correct_options_returns_400(session, client):
    await _make_admin(session)
    token = await _admin_token(client)

    response = await client.post(
        "/questions",
        data={
            "text": "Broken question",
            "options": _options_field(
                [{"text": "A", "is_correct": True}, {"text": "B", "is_correct": True}]
            ),
        },
        headers=_auth(token),
    )

    assert response.status_code == 400


# ------------------------------------------------------------- WARN-3
# (SC-4 / NFR-2 — Cloudinary-failure-doesn't-block-creation — lives in its
# own file, tests/integration/test_question_upload_failure.py, per 011.md's
# verification checklist.)


async def test_invalid_mime_type_returns_400_and_cloudinary_not_called(
    session, client, image_storage_mock
):
    await _make_admin(session)
    token = await _admin_token(client)

    response = await client.post(
        "/questions",
        data={
            "text": "Question with a fake image",
            "options": _options_field(
                [{"text": "A", "is_correct": True}, {"text": "B", "is_correct": False}]
            ),
        },
        # Header lies about the type; the real content is a PDF — the
        # server must sniff magic bytes, not trust this header.
        files={"image": ("q.pdf", _PDF_BYTES, "image/png")},
        headers=_auth(token),
    )

    assert response.status_code == 400
    image_storage_mock.upload.assert_not_called()


async def test_oversized_image_returns_400_and_cloudinary_not_called(
    session, client, image_storage_mock
):
    await _make_admin(session)
    token = await _admin_token(client)

    response = await client.post(
        "/questions",
        data={
            "text": "Question with a huge image",
            "options": _options_field(
                [{"text": "A", "is_correct": True}, {"text": "B", "is_correct": False}]
            ),
        },
        files={"image": ("big.png", _OVERSIZED_PNG_BYTES, "image/png")},
        headers=_auth(token),
    )

    assert response.status_code == 400
    image_storage_mock.upload.assert_not_called()


# ------------------------------------------------------------- list + auth


async def test_list_questions_requires_admin(session, client):
    session.add(
        User(email="user@example.com", password_hash=hash_password("userpw"), role="user")
    )
    await session.commit()
    token = (
        await client.post(
            "/auth/login", json={"email": "user@example.com", "password": "userpw"}
        )
    ).json()["access_token"]

    response = await client.get("/questions", headers=_auth(token))

    assert response.status_code == 403


async def test_list_questions_returns_created_questions(session, client):
    await _make_admin(session)
    token = await _admin_token(client)
    await client.post(
        "/questions",
        data={
            "text": "Q1",
            "options": _options_field(
                [{"text": "A", "is_correct": True}, {"text": "B", "is_correct": False}]
            ),
        },
        headers=_auth(token),
    )

    response = await client.get("/questions", headers=_auth(token))

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["text"] == "Q1"
