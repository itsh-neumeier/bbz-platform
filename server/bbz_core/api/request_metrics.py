"""ASGI middleware that times every HTTP request into the Prometheus histogram
``bbz_http_request_duration_seconds`` (roadmap E22-02, MASTER_PROMPT §23).

Pure ASGI (not ``BaseHTTPMiddleware``) so it adds no buffering. The ``route``
label is the **template** (``/api/v1/events/{event_id}``), rebuilt from the
resolved path with its path-params folded back to ``{name}`` — bounded by the
route table, never the raw path. An unrouted request (404, no match) is labelled
``unmatched`` so a scan / fuzzer cannot blow up the cardinality.
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Awaitable, Callable
from typing import Any

from bbz_core.infra.metrics import observe_request

Scope = dict[str, Any]
Receive = Callable[[], Awaitable[dict[str, Any]]]
Send = Callable[[dict[str, Any]], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


def _route_template(scope: Scope) -> str:
    if scope.get("route") is None:
        return "unmatched"
    path: str = scope.get("path", "")
    for name, value in (scope.get("path_params") or {}).items():
        path = path.replace(str(value), "{" + name + "}", 1)
    return path or "unmatched"


class RequestMetricsMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()
        status = 500

        async def _send(message: dict[str, Any]) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, _send)
        finally:
            # metrics must never break a request
            with contextlib.suppress(Exception):  # pragma: no cover
                observe_request(
                    scope["method"], _route_template(scope), status, time.perf_counter() - start
                )
