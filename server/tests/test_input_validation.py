"""E23-06: every /api/v1 write body forbids unknown fields; oversized body → 413."""

from __future__ import annotations

import os
import typing

import fastapi.routing as fr
import httpx
import pytest
from fastapi.routing import APIRoute
from pydantic import BaseModel

_WRITE = {"POST", "PUT", "PATCH", "DELETE"}
_API_V1 = "/api/v1"

# Writes whose body is deliberately schema-less. The inbound telephony webhook
# takes whatever the provider sends and normalises it downstream
# (`bbz_core.infra.telephony_ingest`); it is bearer-authed and body-size-capped.
_RAW_BODY: set[tuple[str, str]] = {
    ("POST", "/api/v1/telephony/events"),
}


def _walk(router: object) -> list[tuple[str, APIRoute]]:
    out: list[tuple[str, APIRoute]] = []
    for route in getattr(router, "routes", []):
        if isinstance(route, APIRoute):
            path = route.path if route.path.startswith(_API_V1) else _API_V1 + route.path
            out.append((path, route))
        if isinstance(route, fr._IncludedRouter):
            out.extend(_walk(route.original_router))
    return out


def _models(annotation: object) -> list[type[BaseModel]]:
    found: list[type[BaseModel]] = []
    stack = [annotation]
    while stack:
        cur = stack.pop()
        if isinstance(cur, type) and issubclass(cur, BaseModel):
            found.append(cur)
        else:
            stack.extend(typing.get_args(cur))
    return found


def test_every_api_v1_write_body_forbids_unknown_fields() -> None:
    os.environ.setdefault("BBZ_JWT_SECRET", "input-validation-test-secret-32-bytes!!")
    from bbz_core.app import create_app

    offenders: list[str] = []
    checked = 0
    for path, route in _walk(create_app().router):
        for method in route.methods & _WRITE:
            body_field = getattr(route, "body_field", None)
            if body_field is None or (method, path) in _RAW_BODY:
                continue
            models = _models(body_field.field_info.annotation)
            if not models:
                offenders.append(f"{method} {path} (non-model body)")
                continue
            for model in models:
                checked += 1
                if model.model_config.get("extra") != "forbid":
                    offenders.append(f"{method} {path} -> {model.__name__}")

    assert checked > 40, f"walker regressed — only inspected {checked} bodies"
    assert not offenders, f"write bodies that accept unknown fields: {offenders}"


# --- integration -----------------------------------------------------------


@pytest.fixture(autouse=True)
def _env() -> typing.Iterator[None]:
    from bbz_core import settings as settings_mod
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "input-validation-test-secret-32-bytes!!"
    os.environ["BBZ_SESSION_COOKIE_SECURE"] = "false"
    os.environ["BBZ_MAX_REQUEST_BODY_BYTES"] = "1024"  # set before the app is built
    os.environ["BBZ_RATE_LIMIT_LOGIN"] = "0"  # keep the 422 test off the DB
    settings_mod.get_settings.cache_clear()
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    yield
    for key in ("BBZ_MAX_REQUEST_BODY_BYTES", "BBZ_RATE_LIMIT_LOGIN"):
        os.environ.pop(key, None)
    settings_mod.get_settings.cache_clear()
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()


@pytest.fixture(autouse=True)
async def _no_engine_leak() -> typing.AsyncIterator[None]:
    # These tests drive the app without the `db` fixture, so nothing disposes the
    # async engine that an endpoint may lazily create — its pooled asyncpg
    # connections would then surface as ResourceWarnings in a later test.
    yield
    from bbz_core.infra import db as db_mod

    if db_mod.get_engine.cache_info().currsize:
        await db_mod.get_engine().dispose()


async def test_an_oversized_body_is_rejected_before_auth(client: httpx.AsyncClient) -> None:
    r = await client.post(
        "/api/v1/events",
        content=b'{"x":"' + b"A" * 4000 + b'"}',
        headers={"content-type": "application/json", "X-Command-Id": "x"},
    )
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "payload_too_large"


async def test_an_oversized_chunked_body_is_also_rejected(client: httpx.AsyncClient) -> None:
    async def _stream() -> typing.AsyncIterator[bytes]:
        yield b"A" * 4000  # no Content-Length -> the streaming guard must catch it

    r = await client.post(
        "/api/v1/events",
        content=_stream(),
        headers={"content-type": "application/json", "X-Command-Id": "x"},
    )
    assert r.status_code == 413


async def test_a_normal_sized_body_is_not_capped(client: httpx.AsyncClient) -> None:
    # small body -> the cap lets it through; /refresh 401s before any DB call
    r = await client.post(
        "/api/v1/auth/refresh",
        content=b"{}",
        headers={"content-type": "application/json"},
    )
    assert r.status_code != 413


async def test_an_unknown_field_is_rejected_with_422(client: httpx.AsyncClient) -> None:
    r = await client.post(
        "/api/v1/auth/login",
        json={"username": "u", "password": "p", "is_admin": True},
    )
    assert r.status_code == 422
    assert any(d["type"] == "extra_forbidden" for d in r.json()["detail"])
