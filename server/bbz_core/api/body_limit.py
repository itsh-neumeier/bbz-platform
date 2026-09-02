"""Global request-body size cap (E23-06).

A JSON control-plane has no reason to accept a multi-megabyte request. Capping
the body keeps a hostile or buggy client from pinning memory before any handler
runs, and is the guard that will cover file uploads once the platform grows any.

The declared ``Content-Length`` is rejected up front (every real client sends
one). A body with no / an understated length is buffered as it streams and cut
off at the same limit. Either way the client gets **413** with the uniform error
envelope. Nothing in this API streams a request body, so the bounded buffering
costs at most ``max_bytes``.
"""

from __future__ import annotations

import json

from starlette.types import ASGIApp, Message, Receive, Scope, Send

_BODY_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def _declared_length(scope: Scope) -> int | None:
    for key, value in scope.get("headers", []):
        if key == b"content-length":
            try:
                return int(value)
            except ValueError:
                return None
    return None


class BodyLimitMiddleware:
    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or self.max_bytes <= 0
            or scope.get("method", "GET").upper() not in _BODY_METHODS
        ):
            await self.app(scope, receive, send)
            return

        declared = _declared_length(scope)
        if declared is not None and declared > self.max_bytes:
            await self._reject(send)
            return

        body = bytearray()
        while True:
            message = await receive()
            if message["type"] != "http.request":
                # disconnect (or similar) before the body finished — hand it on
                await self._replay(scope, bytes(body), message, receive, send)
                return
            body += message.get("body", b"")
            if len(body) > self.max_bytes:
                await self._reject(send)
                return
            if not message.get("more_body", False):
                break

        await self._replay(scope, bytes(body), None, receive, send)

    async def _replay(
        self,
        scope: Scope,
        body: bytes,
        trailing: Message | None,
        receive: Receive,
        send: Send,
    ) -> None:
        queue: list[Message] = [{"type": "http.request", "body": body, "more_body": False}]
        if trailing is not None:
            queue.append(trailing)

        async def replay_receive() -> Message:
            if queue:
                return queue.pop(0)
            return await receive()

        await self.app(scope, replay_receive, send)

    async def _reject(self, send: Send) -> None:
        body = json.dumps(
            {
                "error": {
                    "code": "payload_too_large",
                    "message": f"request body exceeds {self.max_bytes} bytes",
                    "details": None,
                    "correlation_id": None,
                }
            }
        ).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [(b"content-type", b"application/json")],
            }
        )
        await send({"type": "http.response.body", "body": body})
