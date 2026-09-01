"""E22-01: the no-op OTel seam becomes real tracing.

- one request produces a single connected trace: HTTP server span -> DB spans
  (incl. the outbox write) all share the trace id and hang off the request;
- every structured log line emitted in a request carries `trace_id` / `span_id`;
- `correlation_id` (E04-09) rides along as the `bbz.correlation_id` attribute;
- the OTLP exporter is off by default and switched on by config alone;
- a registered transient secret (E17-06) is scrubbed from exported spans.
"""

from __future__ import annotations

import io
import os
import uuid
from collections.abc import AsyncIterator, Iterator

import httpx
import pytest
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core import telemetry
from bbz_core.redaction import MASK, redacting


@pytest.fixture(scope="module")
def _exporter() -> Iterator[object]:
    """Arm tracing once for the module with an in-memory exporter behind the
    same redaction wrapper production uses."""
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

    os.environ["BBZ_OTEL_ENABLED"] = "true"
    from bbz_core.settings import get_settings

    get_settings.cache_clear()
    telemetry._reset_for_tests()  # other files ran configure_tracing() with it off
    telemetry.configure_tracing()
    assert telemetry._STATE.provider is not None, "tracing did not arm"
    mem = InMemorySpanExporter()
    telemetry._STATE.provider.add_span_processor(
        SimpleSpanProcessor(telemetry._redacting_exporter(mem))
    )
    yield mem
    os.environ["BBZ_OTEL_ENABLED"] = "false"
    get_settings.cache_clear()
    telemetry._reset_for_tests()


@pytest.fixture
def spans(_exporter: object) -> Iterator[object]:
    _exporter.clear()  # type: ignore[attr-defined]
    yield _exporter
    _exporter.clear()  # type: ignore[attr-defined]


@pytest.fixture(autouse=True)
def _fast_auth() -> Iterator[None]:
    from bbz_core.auth import hashing

    os.environ["BBZ_ARGON2_MEMORY_COST_KIB"] = "512"
    os.environ["BBZ_ARGON2_TIME_COST"] = "1"
    os.environ["BBZ_JWT_SECRET"] = "otel-test-secret-at-least-32-bytes-long-ok!"
    os.environ["BBZ_SESSION_COOKIE_SECURE"] = "false"
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()
    yield
    hashing._hasher.cache_clear()
    hashing._dummy_hash.cache_clear()


# --- unit: the config-only exporter toggle --------------------------------


def test_the_otlp_exporter_is_off_by_default() -> None:
    from bbz_core.settings import Settings

    assert telemetry._build_exporter(Settings(otel_traces_exporter="none")) is None


def test_switching_the_exporter_on_needs_config_not_code() -> None:
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    from bbz_core.settings import Settings

    exp = telemetry._build_exporter(
        Settings(
            otel_traces_exporter="otlp",
            otel_exporter_otlp_endpoint="http://collector:4318",
        )
    )
    assert isinstance(exp, OTLPSpanExporter)
    assert exp._endpoint == "http://collector:4318/v1/traces"
    exp.shutdown()


def test_tracing_is_a_clean_noop_when_disabled() -> None:
    from bbz_core.settings import Settings
    from bbz_core.telemetry import _State, current_trace_ids

    saved = telemetry._STATE
    telemetry._STATE = _State()
    try:
        assert telemetry.configure_tracing(Settings(otel_enabled=False)) is False
        assert current_trace_ids() is None
    finally:
        telemetry._STATE = saved


# --- integration: a connected trace across API -> DB -> Outbox ------------


async def _make_user(s: AsyncSession, username: str, perms: list[str]) -> uuid.UUID:
    from sqlalchemy import select

    from bbz_core.auth.hashing import hash_password
    from bbz_core.infra.models.identity import AuthIdentity, LocalCredential, User
    from bbz_core.infra.models.rbac import Permission, Role, RolePermission, UserRole

    u = User(display_name=username.title())
    s.add(u)
    await s.flush()
    ident = AuthIdentity(user_id=u.id, provider="local", subject=username)
    s.add(ident)
    await s.flush()
    pw = hash_password("Wolke7-Bahnhof!x")
    s.add(LocalCredential(auth_identity_id=ident.id, password_hash=pw))
    if perms:
        role = Role(key=f"r-{username}", name="R")
        s.add(role)
        await s.flush()
        for key in perms:
            pid = (
                await s.execute(select(Permission.id).where(Permission.key == key))
            ).scalar_one_or_none()
            if pid is None:
                p = Permission(key=key, area=key.split(".")[0])
                s.add(p)
                await s.flush()
                pid = p.id
            s.add(RolePermission(role_id=role.id, permission_id=pid, scope="global"))
        s.add(UserRole(user_id=u.id, role_id=role.id))
    await s.commit()
    return u.id


async def _login(c: httpx.AsyncClient, username: str) -> None:
    r = await c.post(
        "/api/v1/auth/login", json={"username": username, "password": "Wolke7-Bahnhof!x"}
    )
    assert r.status_code == 200, r.text


@pytest.fixture
async def env(
    client: httpx.AsyncClient, db: object
) -> AsyncIterator[tuple[httpx.AsyncClient, AsyncSession]]:
    assert isinstance(db, AsyncSession)
    yield client, db


async def test_a_takeover_request_is_one_connected_trace(
    env: tuple[httpx.AsyncClient, AsyncSession], spans: object
) -> None:
    client, s = env
    await _make_user(s, "disp", ["events.create", "events.assign"])
    owner = await _make_user(s, "owner", [])
    await _make_user(s, "taker", ["events.takeover"])

    await _login(client, "disp")
    eid = (
        await client.post(
            "/api/v1/events",
            json={"title": "Oberleitungsschaden", "priority": "critical"},
            headers={"X-Command-Id": str(uuid.uuid4())},
        )
    ).json()["id"]
    r = await client.post(
        f"/api/v1/events/{eid}/assign",
        json={"target_user_id": str(owner)},
        headers={"X-Command-Id": str(uuid.uuid4()), "X-Expected-Version": "1"},
    )
    assert r.status_code == 200, r.text

    taker = httpx.AsyncClient(transport=client._transport, base_url="http://testserver")  # type: ignore[attr-defined]
    await _login(taker, "taker")
    spans.clear()  # type: ignore[attr-defined]  # only look at the takeover
    cid = f"corr-{uuid.uuid4()}"
    r = await taker.post(
        f"/api/v1/events/{eid}/takeover",
        headers={
            "X-Command-Id": str(uuid.uuid4()),
            "X-Expected-Version": "2",
            "X-Correlation-Id": cid,
        },
    )
    assert r.status_code == 200, r.text
    await taker.aclose()

    finished = spans.get_finished_spans()  # type: ignore[attr-defined]
    server = [sp for sp in finished if sp.kind.name == "SERVER"]
    db_spans = [sp for sp in finished if (sp.attributes or {}).get("db.system")]

    assert len(server) == 1, [sp.name for sp in finished]
    assert db_spans, "no DB spans captured for the takeover"

    # one trace, and every DB span hangs off the request
    trace_id = server[0].context.trace_id
    assert {sp.context.trace_id for sp in finished} == {trace_id}
    assert all(sp.parent is not None for sp in db_spans)

    # correlation_id (E04-09) rode along on the request span
    assert server[0].attributes.get(telemetry.CORRELATION_ID_ATTRIBUTE) == cid

    # the outbox INSERT is one of the DB writes in this same trace
    statements = " ".join((sp.attributes or {}).get("db.statement", "") for sp in db_spans)
    assert "external_action_outbox" in statements.lower()


def test_log_lines_carry_the_active_trace_id(spans: object) -> None:
    """`_add_trace_context` stamps a line emitted while a span is active; once
    the span ends the same logger emits neither field."""
    from opentelemetry import trace

    from bbz_core.logging import _add_trace_context

    buf = io.StringIO()
    logger = structlog.wrap_logger(
        structlog.PrintLogger(buf),
        processors=[_add_trace_context, structlog.processors.JSONRenderer()],
    )

    tracer = trace.get_tracer("test")
    with tracer.start_as_current_span("unit") as span:
        want = f"{span.get_span_context().trace_id:032x}"
        logger.info("inside")
    inside = buf.getvalue()

    buf.seek(0), buf.truncate()
    logger.info("outside")
    outside = buf.getvalue()

    assert want in inside and '"span_id"' in inside
    assert "trace_id" not in outside


# --- redaction net --------------------------------------------------------


def test_a_registered_secret_is_scrubbed_from_exported_spans(spans: object) -> None:
    from opentelemetry import trace

    sentinel = "9A9A9A#9A"
    tracer = trace.get_tracer("test")
    with redacting(sentinel), tracer.start_as_current_span("guarded") as span:
        span.set_attribute("payload", f"gateway rejected tone {sentinel}")
        span.record_exception(RuntimeError(f"tone {sentinel} refused"))

    exported = spans.get_finished_spans()  # type: ignore[attr-defined]
    blob = ""
    for sp in exported:
        blob += str(dict(sp.attributes or {}))
        for ev in sp.events:
            blob += str(dict(ev.attributes or {}))
    assert sentinel not in blob
    assert MASK in blob
