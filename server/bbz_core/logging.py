"""Structured logging setup.

JSON logs in every non-local environment so the platform is observable from day
one (MASTER_PROMPT §23). A ``correlation_id`` context var is threaded through so
request/command/event logs can be tied together later.
"""

from __future__ import annotations

import logging
from contextvars import ContextVar
from typing import Any, cast

import structlog
from structlog.types import EventDict, WrappedLogger

from bbz_core.redaction import scrub
from bbz_core.telemetry import current_trace_ids

correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def _add_correlation_id(
    _logger: WrappedLogger, _method_name: str, event_dict: EventDict
) -> EventDict:
    cid = correlation_id.get()
    if cid is not None:
        event_dict.setdefault("correlation_id", cid)
    return event_dict


def _add_trace_context(
    _logger: WrappedLogger, _method_name: str, event_dict: EventDict
) -> EventDict:
    """Tie a log line to its OpenTelemetry span (E22-01). No-op when tracing is
    off or the line is emitted outside a request."""
    ids = current_trace_ids()
    if ids is not None:
        event_dict.setdefault("trace_id", ids[0])
        event_dict.setdefault("span_id", ids[1])
    return event_dict


def _redact(_logger: WrappedLogger, _method_name: str, event_dict: EventDict) -> EventDict:
    """Mask any transient registered secret (E17-06) in the rendered log line."""
    return scrub(event_dict)


def configure_logging(*, level: str = "INFO", json: bool = True) -> None:
    renderer: Any = structlog.processors.JSONRenderer() if json else structlog.dev.ConsoleRenderer()
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            _add_correlation_id,
            _add_trace_context,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            _redact,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.getLevelNamesMapping().get(level.upper(), logging.INFO)
        ),
        cache_logger_on_first_use=True,
    )
    logging.basicConfig(format="%(message)s", level=level.upper())


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return cast("structlog.stdlib.BoundLogger", structlog.get_logger(name))
