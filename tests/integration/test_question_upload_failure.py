"""T011 — SC-4 / NFR-2: a Cloudinary failure must not block question creation.

Unexecuted (no Python/Docker in the authoring environment). Named to match
011.md's verification checklist (`pytest
tests/integration/test_question_upload_failure.py`). Same
ASGI-through-httpx pattern as `tests/integration/test_questions.py`.
"""

import json
from unittest.mock import AsyncMock

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.v1.routes.auth import router as auth_router
from app.api.v1.routes.questions import get_image_storage
from app.api.v1.routes.questions import router as questions_router
from app.ports.image_storage import ImageStoragePort, UploadError
from app.core.security import hash_password
from app.models.user import User
from app.core.database import get_session

_PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"fake-png-body"


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


async def _admin_token(session, client) -> str:
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
    return response.json()["access_token"]


async def test_cloudinary_failure_still_saves_question_without_image(
    session, client, image_storage_mock
):
    token = await _admin_token(session, client)
    image_storage_mock.upload.side_effect = UploadError("Cloudinary timeout")

    response = await client.post(
        "/questions",
        data={
            "text": "Question with flaky image host",
            "options": json.dumps(
                [{"text": "A", "is_correct": True}, {"text": "B", "is_correct": False}]
            ),
        },
        files={"image": ("q.png", _PNG_BYTES, "image/png")},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["image_url"] is None
    assert body["image_upload_warning"]
    image_storage_mock.upload.assert_called_once()
