"""OpenTelemetry preparation.

MASTER_PROMPT §6/§23 require OTel to be *prepared*, not fully wired in the
foundation phase. This module is the single seam where tracing/metrics get
enabled later (ADR-0014). Today it is a documented no-op.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastapi import FastAPI


def instrument_app(app: FastAPI) -> None:
    """No-op today. Phase-2+ attaches OTLP exporters and FastAPI instrumentation here."""
    return None
