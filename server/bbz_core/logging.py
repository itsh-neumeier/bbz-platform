"""Structured logging pipeline (E22-03, MASTER_PROMPT §6/§22).

Every line is JSON (outside ``local``) with a consistent field set:
``timestamp`` ``level`` ``event`` ``node_id`` and — when the line is emitted
inside a request — ``correlation_id`` (E04-09), ``trace_id`` / ``span_id``
(E22-01) and ``user_id``.

Two redaction layers run before the renderer:
- :func:`_redact_keys` masks a value whose **key** looks sensitive
  (``password`` / ``token`` / ``authorization`` / ``dtmf`` / …), recursively;
- :func:`_redact` masks any **transient** secret registered with
  ``bbz_core.redaction.redacting(...)`` (E17-06), by substring.

``BBZ_LOG_LEVELS`` steers the level per module; ``BBZ_LOG_SAMPLE`` drops a
fraction of a named noisy event; ``BBZ_LOG_FILE`` tees the JSON lines to a file
for a sidecar to ship (E22-03 does not operate a log backend).
"""

from __future__ import annotations

import contextlib
import logging
import random
import sys
from contextvars import ContextVar
from typing import Any, TextIO, cast

import structlog
from structlog.types import EventDict, WrappedLogger

from bbz_core.redaction import scrub
from bbz_core.telemetry import current_trace_ids

correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)
user_id: ContextVar[str | None] = ContextVar("bbz_user_id", default=None)

#: substrings that make a key sensitive (lower-cased comparison)
_SENSITIVE_KEY_PARTS = (
    "password",
    "passwd",
    "secret",
    "token",
    "authorization",
    "api_key",
    "apikey",
    "private_key",
    "credential",
    "dtmf",
    "otp",
    "recovery_code",
    "session_key",
)
_MASK = "[redacted]"
_MAX_DEPTH = 12

_NODE_ID = "unknown"
_MODULE_LEVELS: list[tuple[str, int]] = []
_SAMPLE_RATES: dict[str, float] = {}
_LOG_FILE_HANDLE: TextIO | None = None


class _Tee:
    """Write every log line to several streams — stdout plus, when
    ``BBZ_LOG_FILE`` is set, a file a sidecar ships (E22-03 runs no backend)."""

    def __init__(self, *streams: TextIO) -> None:
        self._streams = streams

    def write(self, data: str) -> int:
        for stream in self._streams:
            # a broken sink must not kill logging
            with contextlib.suppress(Exception):  # pragma: no cover
                stream.write(data)
        return len(data)

    def flush(self) -> None:
        for stream in self._streams:
            with contextlib.suppress(Exception):  # pragma: no cover
                stream.flush()


# --------------------------------------------------------------------------
# context fields
# --------------------------------------------------------------------------
def _add_node_id(_l: WrappedLogger, _m: str, event_dict: EventDict) -> EventDict:
    event_dict.setdefault("node_id", _NODE_ID)
    return event_dict


def _add_correlation_id(_l: WrappedLogger, _m: str, event_dict: EventDict) -> EventDict:
    cid = correlation_id.get()
    if cid is not None:
        event_dict.setdefault("correlation_id", cid)
    return event_dict


def _add_user_id(_l: WrappedLogger, _m: str, event_dict: EventDict) -> EventDict:
    uid = user_id.get()
    if uid is not None:
        event_dict.setdefault("user_id", uid)
    return event_dict


def _add_trace_context(_l: WrappedLogger, _m: str, event_dict: EventDict) -> EventDict:
    """Tie a log line to its OpenTelemetry span (E22-01). No-op when tracing is
    off or the line is emitted outside a request."""
    ids = current_trace_ids()
    if ids is not None:
        event_dict.setdefault("trace_id", ids[0])
        event_dict.setdefault("span_id", ids[1])
    return event_dict


# --------------------------------------------------------------------------
# redaction
# --------------------------------------------------------------------------
def _sensitive_key(key: str) -> bool:
    k = key.lower()
    return any(part in k for part in _SENSITIVE_KEY_PARTS)


def _redact_value(value: Any, depth: int) -> Any:
    if depth >= _MAX_DEPTH:
        return value
    if isinstance(value, dict):
        return {
            k: (_MASK if isinstance(k, str) and _sensitive_key(k) else _redact_value(v, depth + 1))
            for k, v in value.items()
        }
    if isinstance(value, (list, tuple)):
        return type(value)(_redact_value(v, depth + 1) for v in value)
    return value


def _redact_keys(_l: WrappedLogger, _m: str, event_dict: EventDict) -> EventDict:
    """Mask a value whose key looks sensitive — passwords, tokens, DTMF codes."""
    return cast("EventDict", _redact_value(dict(event_dict), 0))


def _redact(_l: WrappedLogger, _m: str, event_dict: EventDict) -> EventDict:
    """Mask any transient registered secret (E17-06) — substring match."""
    return scrub(event_dict)


# --------------------------------------------------------------------------
# per-module level + sampling
# --------------------------------------------------------------------------
_LEVEL_NAMES = logging.getLevelNamesMapping()


def _level_filter(_l: WrappedLogger, method_name: str, event_dict: EventDict) -> EventDict:
    """Drop the event if its level is below the threshold configured for its
    module (``BBZ_LOG_LEVELS``). The coarse ``make_filtering_bound_logger`` gate
    already dropped everything below the lowest configured level."""
    if not _MODULE_LEVELS:
        return event_dict
    name = event_dict.get("logger")
    if not isinstance(name, str):
        return event_dict
    threshold = next((lvl for prefix, lvl in _MODULE_LEVELS if name.startswith(prefix)), None)
    if threshold is None:
        return event_dict
    if _LEVEL_NAMES.get(method_name.upper(), logging.INFO) < threshold:
        raise structlog.DropEvent
    return event_dict


def _sampler(_l: WrappedLogger, _m: str, event_dict: EventDict) -> EventDict:
    """Keep a named noisy event only ``rate`` of the time (``BBZ_LOG_SAMPLE``)."""
    if not _SAMPLE_RATES:
        return event_dict
    rate = _SAMPLE_RATES.get(str(event_dict.get("event")))
    if rate is not None and random.random() >= rate:
        raise structlog.DropEvent
    return event_dict


# --------------------------------------------------------------------------
# config
# --------------------------------------------------------------------------
def _parse_levels(raw: str) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    for pair in raw.split(","):
        module, _, level = pair.partition("=")
        module, level = module.strip(), level.strip().upper()
        if module and level in _LEVEL_NAMES:
            out.append((module, _LEVEL_NAMES[level]))
    # longest prefix first, so a specific module beats a broad one
    out.sort(key=lambda t: len(t[0]), reverse=True)
    return out


def _parse_sample(raw: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for pair in raw.split(","):
        name, _, rate = pair.partition("=")
        name, rate = name.strip(), rate.strip()
        if name and rate:
            try:
                out[name] = min(max(float(rate), 0.0), 1.0)
            except ValueError:
                continue
    return out


def configure_logging(
    *,
    level: str = "INFO",
    json: bool = True,
    node_id: str = "unknown",
    module_levels: str = "",
    sample: str = "",
    log_file: str = "",
    stream: TextIO | None = None,
) -> None:
    global _NODE_ID, _MODULE_LEVELS, _SAMPLE_RATES, _LOG_FILE_HANDLE
    _NODE_ID = node_id
    _MODULE_LEVELS = _parse_levels(module_levels)
    _SAMPLE_RATES = _parse_sample(sample)

    if stream is None:
        if _LOG_FILE_HANDLE is not None:
            _LOG_FILE_HANDLE.close()
            _LOG_FILE_HANDLE = None
        if log_file:
            _LOG_FILE_HANDLE = open(log_file, "a", encoding="utf-8")  # noqa: SIM115
            stream = cast("TextIO", _Tee(sys.stdout, _LOG_FILE_HANDLE))

    renderer: Any = structlog.processors.JSONRenderer() if json else structlog.dev.ConsoleRenderer()
    # the coarse gate must sit at the lowest level anyone wants
    floor = min(
        [_LEVEL_NAMES.get(level.upper(), logging.INFO)] + [lvl for _, lvl in _MODULE_LEVELS]
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            _level_filter,
            _sampler,
            _add_node_id,
            _add_correlation_id,
            _add_user_id,
            _add_trace_context,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            _redact_keys,
            _redact,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(floor),
        logger_factory=structlog.PrintLoggerFactory(file=stream),
        cache_logger_on_first_use=stream is None,
    )
    logging.basicConfig(format="%(message)s", level=level.upper(), force=True)


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    logger = structlog.get_logger()
    if name:
        logger = logger.bind(logger=name)  # so _level_filter can key off the module
    return cast("structlog.stdlib.BoundLogger", logger)
