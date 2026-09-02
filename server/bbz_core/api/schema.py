"""Shared request-schema base (E23-06).

Every ``/api/v1`` write body must reject unknown fields, so an over-posting
attacker cannot smuggle a value past a partial whitelist and the API surface
stays exactly what the model declares. ``tests/test_input_validation.py`` walks
the OpenAPI schema and fails the build if a write body is not ``extra="forbid"``.

New request models should subclass :class:`StrictModel`; the older ad-hoc
``model_config = ConfigDict(extra="forbid")`` on a plain ``BaseModel`` is
equivalent and still accepted by the contract test.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class StrictModel(BaseModel):
    """A request body that rejects unknown fields with a 422."""

    model_config = ConfigDict(extra="forbid")
