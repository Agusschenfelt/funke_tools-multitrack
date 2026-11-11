"""Reject oversized request bodies before they are buffered and parsed.

Pure ASGI so the limit also holds for chunked bodies without a ``Content-Length``. The upload
route (``POST /songs``) is exempt: it streams to disk and enforces ``MAX_UPLOAD_MB`` itself.
"""

import json

from starlette.types import ASGIApp, Message, Receive, Scope, Send

MAX_JSON_BODY_BYTES = 1024 * 1024
UPLOAD_PATH = "/songs"

_BODY = json.dumps({"detail": "request body too large"}).encode()


class BodyLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int = MAX_JSON_BODY_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or (
            scope["method"] == "POST" and scope["path"].rstrip("/") == UPLOAD_PATH
        ):
            await self.app(scope, receive, send)
            return
        declared = dict(scope["headers"]).get(b"content-length")
        if declared is not None and declared.isdigit() and int(declared) > self.max_bytes:
            await self._reject(send)
            return

        received = 0
        rejected = False

        async def counting_receive() -> Message:
            # Frameworks wrap errors raised while reading the body into a 400, so answer 413 here
            # and report a disconnect; whatever the app sends afterwards is dropped.
            nonlocal received, rejected
            if rejected:
                return {"type": "http.disconnect"}
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    rejected = True
                    await self._reject(send)
                    return {"type": "http.disconnect"}
            return message

        async def guarded_send(message: Message) -> None:
            if not rejected:
                await send(message)

        await self.app(scope, counting_receive, guarded_send)

    @staticmethod
    async def _reject(send: Send) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(_BODY)).encode()),
                    (b"connection", b"close"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": _BODY})
