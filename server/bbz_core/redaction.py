"""Transient secret redaction across every observability sink (roadmap E17-06).

The door-open flow decrypts its DTMF sequence into a local (ADR-0025) and, by
construction, keeps it out of audit rows, domain events, outbox payloads and
logs. This is the defense-in-depth net: ``with redacting(<secret>):`` registers a
value for the duration of a call, and every sink runs :func:`scrub` on what it is
about to persist or emit — so a value that leaks through some new path (a
provider echoing the code in an exception message, say) is masked everywhere.

Stdlib only, no ``bbz_core`` imports — safe to import from ``bbz_core.logging``
and every layer.
"""

from __future__ import annotations

import contextlib
from collections.abc import Iterator
from contextvars import ContextVar
from typing import Any, cast

#: what a registered secret is replaced with (ASCII — survives JSON escaping)
MASK = "[redacted]"

#: values shorter than this are never registered (an empty / 1-char "secret"
#: would mask far too much)
_MIN_LEN = 3
_MAX_DEPTH = 10

_active: ContextVar[frozenset[str]] = ContextVar("bbz_active_secrets", default=frozenset())


@contextlib.contextmanager
def redacting(*secrets: str | None) -> Iterator[None]:
    """Register ``secrets`` so every :func:`scrub` call within this context masks
    them. Nesting unions; too-short / empty values are ignored."""
    add = frozenset(s for s in secrets if s is not None and len(s) >= _MIN_LEN)
    if not add:
        yield
        return
    token = _active.set(_active.get() | add)
    try:
        yield
    finally:
        _active.reset(token)


def active_secret_count() -> int:
    """How many secrets are registered on the current context (tests / asserts)."""
    return len(_active.get())


def scrub[T](value: T) -> T:
    """Return ``value`` with every registered secret substring masked.

    A no-op returning the same object when nothing is registered, so it is safe
    on every hot path (audit write, event append, log emit).
    """
    secrets = _active.get()
    if not secrets:
        return value
    return cast("T", _scrub(value, secrets, 0))


def _scrub(value: Any, secrets: frozenset[str], depth: int) -> Any:
    if isinstance(value, str):
        for s in secrets:
            if s in value:
                value = value.replace(s, MASK)
        return value
    if depth >= _MAX_DEPTH:
        return value
    if isinstance(value, dict):
        return {k: _scrub(v, secrets, depth + 1) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub(v, secrets, depth + 1) for v in value]
    if type(value) is tuple:
        return tuple(_scrub(v, secrets, depth + 1) for v in value)
    return value
