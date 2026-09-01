"""OpenTelemetry tracing (roadmap E22-01, ADR-0028).

A documented no-op through the foundation phase; this is the real wiring.
:func:`instrument_app` stays the single seam ``bbz_core.app`` calls.

- SDK init with a ``Resource`` from settings; ``ParentBased(TraceIdRatioBased)``
  sampler (all-on by default — with the exporter off that is free).
- Instrumentation: FastAPI per app (:func:`instrument_app`), httpx process-wide,
  SQLAlchemy per engine (:func:`instrument_engine`, wired from
  :mod:`bbz_core.infra.db` — the instrumentor's module-level patch can't see a
  ``from ... import create_async_engine`` binding).
- OTLP/HTTP exporter, **off unless** ``BBZ_OTEL_TRACES_EXPORTER=otlp`` — the
  exporter is toggled by config, never code (AC).
- ``correlation_id`` (E04-09) rides along as the ``bbz.correlation_id`` span
  attribute; ``trace_id`` / ``span_id`` land in every structured log line
  (see :mod:`bbz_core.logging`).
- Redaction: the exporter is wrapped so every span's attributes and event
  attributes pass through :func:`bbz_core.redaction.scrub` — the same net every
  other sink uses (E17-06). Auto-instrumentation captures no request bodies or
  headers; ``db.statement`` is the parameterised SQL (no bound values).
"""

from __future__ import annotations

import logging as _logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from bbz_core import __version__
from bbz_core.redaction import scrub
from bbz_core.settings import Settings, get_settings

if TYPE_CHECKING:
    from fastapi import FastAPI
    from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
    from opentelemetry.sdk.trace.export import SpanExporter
    from sqlalchemy.ext.asyncio import AsyncEngine

_log = _logging.getLogger(__name__)

#: our own span attribute carrying the request/command correlation id (E04-09)
CORRELATION_ID_ATTRIBUTE = "bbz.correlation_id"


@dataclass
class _State:
    provider: TracerProvider | None = None
    configured: bool = False
    process_instrumented: bool = False


_STATE = _State()


# --------------------------------------------------------------------------
# wiring
# --------------------------------------------------------------------------
def configure_tracing(settings: Settings | None = None) -> bool:
    """Build + install the global ``TracerProvider`` and process-wide
    instrumentation. Idempotent. Returns whether tracing is active."""
    if _STATE.configured:
        return _STATE.provider is not None

    s = settings or get_settings()
    _STATE.configured = True
    if not s.otel_enabled:
        return False

    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.sampling import ParentBased, TraceIdRatioBased

    resource = Resource.create(
        {
            "service.name": s.service_name,
            "service.version": __version__,
            "service.instance.id": s.node_id,
            "deployment.environment": s.environment,
        }
    )
    ratio = min(max(s.otel_traces_sampler_ratio, 0.0), 1.0)
    provider = TracerProvider(resource=resource, sampler=ParentBased(TraceIdRatioBased(ratio)))

    exporter = _build_exporter(s)
    if exporter is not None:
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        provider.add_span_processor(BatchSpanProcessor(_redacting_exporter(exporter)))

    trace.set_tracer_provider(provider)
    _STATE.provider = provider
    _instrument_process(provider)

    # an engine built before tracing armed (unusual, but possible in tests) is
    # picked up here so it is not left untraced
    from bbz_core.infra.db import get_engine

    if get_engine.cache_info().currsize:
        instrument_engine(get_engine())
    return True


def instrument_app(app: FastAPI) -> None:
    """Attach FastAPI request tracing to ``app``. No-op when tracing is off or
    the app is already instrumented (tests build many apps in one process)."""
    if not configure_tracing():
        return

    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    if getattr(app, "_is_instrumented_by_opentelemetry", False):
        return
    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=_STATE.provider,
        # capture nothing beyond method / route / status / peer — no headers,
        # no bodies (redaction: the request may carry tokens / DTMF codes).
        exclude_spans=["receive", "send"],
    )


def shutdown_tracing() -> None:
    """Flush pending spans on app shutdown (lifespan ``finally``)."""
    if _STATE.provider is not None:
        _STATE.provider.shutdown()


def _instrument_process(provider: TracerProvider) -> None:
    if _STATE.process_instrumented:
        return
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

    HTTPXClientInstrumentor().instrument(tracer_provider=provider)
    _STATE.process_instrumented = True


def instrument_engine(engine: AsyncEngine) -> None:
    """Attach SQLAlchemy statement tracing to one async engine. Called by
    :func:`bbz_core.infra.db.get_engine` for every engine it builds — a
    ``from ... import create_async_engine`` binding is invisible to the
    instrumentor's module-level patch, so we wire each engine directly.
    Idempotent; a no-op when tracing is off."""
    if _STATE.provider is None:
        return
    from opentelemetry.instrumentation.sqlalchemy.engine import EngineTracer
    from opentelemetry.metrics import get_meter
    from opentelemetry.trace import get_tracer

    sync_engine = engine.sync_engine
    if getattr(sync_engine, "_bbz_otel_traced", False):
        return
    tracer = get_tracer("bbz_core.infra.db", tracer_provider=_STATE.provider)
    usage = get_meter("bbz_core.infra.db").create_up_down_counter(
        "db.client.connections.usage",
        unit="connections",
        description="connections currently in the pool, by state",
    )
    EngineTracer(tracer, sync_engine, usage)  # type: ignore[no-untyped-call]
    sync_engine._bbz_otel_traced = True  # type: ignore[attr-defined]


def _build_exporter(s: Settings) -> SpanExporter | None:
    if s.otel_traces_exporter != "otlp":
        return None
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter

    kwargs: dict[str, Any] = {}
    endpoint = s.otel_exporter_otlp_endpoint.strip().rstrip("/")
    if endpoint:
        kwargs["endpoint"] = (
            endpoint if endpoint.endswith("/v1/traces") else f"{endpoint}/v1/traces"
        )
    headers = _parse_headers(s.otel_exporter_otlp_headers)
    if headers:
        kwargs["headers"] = headers
    return OTLPSpanExporter(**kwargs)


def _parse_headers(raw: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for pair in raw.split(","):
        key, _, value = pair.partition("=")
        key, value = key.strip(), value.strip()
        if key and value:
            out[key] = value
    return out


# --------------------------------------------------------------------------
# correlation-id  <->  trace-id
# --------------------------------------------------------------------------
def record_correlation_id(correlation_id: str) -> None:
    """Stamp ``correlation_id`` onto the active server span (called from the
    correlation-id middleware). No-op when tracing is off."""
    if _STATE.provider is None:
        return
    from opentelemetry import trace

    span = trace.get_current_span()
    if span.is_recording():
        span.set_attribute(CORRELATION_ID_ATTRIBUTE, scrub(correlation_id))


def current_trace_ids() -> tuple[str, str] | None:
    """``(trace_id_hex, span_id_hex)`` for the current span, or ``None`` when
    there is no valid span (tracing off / outside a request)."""
    from opentelemetry import trace

    ctx = trace.get_current_span().get_span_context()
    if not ctx.is_valid:
        return None
    return f"{ctx.trace_id:032x}", f"{ctx.span_id:016x}"


# --------------------------------------------------------------------------
# redaction net  (E17-06: every sink runs scrub)
# --------------------------------------------------------------------------
def _scrub_span(span: ReadableSpan) -> ReadableSpan:
    from opentelemetry.sdk.trace import Event, ReadableSpan

    attrs = dict(span.attributes or {})
    new_attrs = {k: scrub(v) for k, v in attrs.items()}

    events = list(span.events)
    new_events: list[Event] = []
    events_changed = False
    for event in events:
        ea = dict(event.attributes or {})
        nea = {k: scrub(v) for k, v in ea.items()}
        events_changed = events_changed or nea != ea
        new_events.append(Event(name=event.name, attributes=nea, timestamp=event.timestamp))

    if new_attrs == attrs and not events_changed:
        return span
    return ReadableSpan(
        name=span.name,
        context=span.context,
        parent=span.parent,
        resource=span.resource,
        attributes=new_attrs,
        events=new_events,
        links=span.links,
        kind=span.kind,
        status=span.status,
        start_time=span.start_time,
        end_time=span.end_time,
        instrumentation_scope=span.instrumentation_scope,
    )


def _redacting_exporter(inner: SpanExporter) -> SpanExporter:
    """Wrap ``inner`` so every span passes through
    :func:`bbz_core.redaction.scrub` before export. A no-op in the common case
    (nothing registered); the net is for a transient secret (``redacting(...)``)
    a provider echoes into an exception message while a span is open."""
    from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

    class _RedactingSpanExporter(SpanExporter):
        def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
            return inner.export([_scrub_span(s) for s in spans])

        def shutdown(self) -> None:
            inner.shutdown()

        def force_flush(self, timeout_millis: int = 30_000) -> bool:
            return inner.force_flush(timeout_millis)

    return _RedactingSpanExporter()


# --------------------------------------------------------------------------
# test seam
# --------------------------------------------------------------------------
def _reset_for_tests() -> None:
    """Undo process-wide instrumentation + forget the provider. Tests only."""
    if _STATE.process_instrumented:
        import contextlib

        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        with contextlib.suppress(Exception):  # pragma: no cover - best effort
            HTTPXClientInstrumentor().uninstrument()
    if _STATE.provider is not None:
        _STATE.provider.shutdown()
    _STATE.provider = None
    _STATE.configured = False
    _STATE.process_instrumented = False
