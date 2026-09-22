from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send


class _RequestBodyTooLarge(Exception):
    pass


class MaxBodySizeMiddleware:
    def __init__(self, app: ASGIApp, max_body_size: int) -> None:
        self.app = app
        self.max_body_size = max_body_size

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        content_length = Request(scope).headers.get("content-length")
        if content_length is not None and int(content_length) > self.max_body_size:
            await self._reject(scope, receive, send)
            return

        total = 0

        async def limited_receive():
            nonlocal total
            message = await receive()
            if message["type"] == "http.request":
                total += len(message.get("body", b""))
                if total > self.max_body_size:
                    raise _RequestBodyTooLarge()
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _RequestBodyTooLarge:
            await self._reject(scope, receive, send)

    async def _reject(self, scope: Scope, receive: Receive, send: Send) -> None:
        response = PlainTextResponse("Request body too large", status_code=413)
        await response(scope, receive, send)
