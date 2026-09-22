"""`MaxBodySizeMiddleware` — hard cap on request body size (DoS guard).

Uses a throwaway app + a tiny limit so both the fast `Content-Length`
rejection path and the streaming byte-count path are exercised without
needing to actually send megabytes of data.
"""

import pytest_asyncio
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient

from app.core.middleware import MaxBodySizeMiddleware

_MAX_BODY_SIZE = 10


def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(MaxBodySizeMiddleware, max_body_size=_MAX_BODY_SIZE)

    @app.post("/echo")
    async def echo(request: Request):
        body = await request.body()
        return {"received": len(body)}

    return app


@pytest_asyncio.fixture
async def client():
    app = _build_app()
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


async def test_body_within_limit_is_accepted(client):
    response = await client.post("/echo", content=b"x" * _MAX_BODY_SIZE)

    assert response.status_code == 200
    assert response.json() == {"received": _MAX_BODY_SIZE}


async def test_content_length_over_limit_is_rejected(client):
    response = await client.post("/echo", content=b"x" * (_MAX_BODY_SIZE + 1))

    assert response.status_code == 413


async def test_streamed_body_without_content_length_over_limit_is_rejected(client):
    async def body_stream():
        for _ in range(_MAX_BODY_SIZE + 1):
            yield b"x"

    response = await client.post("/echo", content=body_stream())

    assert response.status_code == 413
