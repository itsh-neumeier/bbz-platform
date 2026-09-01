"""The one HTTP seam the OIDC flow needs (roadmap E21-01).

Discovery, JWKS and the token exchange are the only outbound calls. The default
implementation is stdlib ``urllib`` run in a worker thread — no new runtime
dependency (same choice as the DWD adapter, ADR-0026). Tests inject a stub.

Only ``https`` endpoints are accepted.
"""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Protocol

from bbz_core.auth.oidc.errors import OidcDiscoveryError, OidcTokenError

_MAX_BYTES = 512 * 1024
_TIMEOUT = 10


class OidcHttp(Protocol):
    async def get_json(self, url: str) -> dict[str, Any]: ...

    async def post_form(self, url: str, data: dict[str, str]) -> dict[str, Any]: ...


class UrllibOidcHttp:
    def __init__(self, *, timeout: int = _TIMEOUT) -> None:
        self._timeout = timeout

    async def get_json(self, url: str) -> dict[str, Any]:
        return await asyncio.to_thread(self._get_json, url)

    async def post_form(self, url: str, data: dict[str, str]) -> dict[str, Any]:
        return await asyncio.to_thread(self._post_form, url, data)

    def _get_json(self, url: str) -> dict[str, Any]:
        _require_https(url, OidcDiscoveryError)
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw: bytes = resp.read(_MAX_BYTES + 1)
        except (OSError, ValueError) as exc:
            raise OidcDiscoveryError(f"GET {url} failed: {exc}") from exc
        return _parse(raw, url, OidcDiscoveryError)

    def _post_form(self, url: str, data: dict[str, str]) -> dict[str, Any]:
        _require_https(url, OidcTokenError)
        body = urllib.parse.urlencode(data).encode("ascii")
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout) as resp:
                raw = resp.read(_MAX_BYTES + 1)
        except urllib.error.HTTPError as exc:
            # a 4xx from the token endpoint still carries a JSON error body
            payload = exc.read(_MAX_BYTES + 1)
            if payload:
                return _parse(payload, url, OidcTokenError)
            raise OidcTokenError(f"POST {url} → HTTP {exc.code}") from exc
        except (OSError, ValueError) as exc:
            raise OidcTokenError(f"POST {url} failed: {exc}") from exc
        return _parse(raw, url, OidcTokenError)


def _require_https(url: str, err: type[Exception]) -> None:
    if urllib.parse.urlparse(url).scheme != "https":
        raise err(f"refusing a non-HTTPS OIDC endpoint: {url}")


def _parse(raw: bytes, url: str, err: type[Exception]) -> dict[str, Any]:
    if len(raw) > _MAX_BYTES:
        raise err(f"response from {url} exceeds {_MAX_BYTES} bytes")
    try:
        obj = json.loads(raw)
    except ValueError as exc:
        raise err(f"response from {url} is not JSON: {exc}") from exc
    if not isinstance(obj, dict):
        raise err(f"response from {url} is not a JSON object")
    return obj
