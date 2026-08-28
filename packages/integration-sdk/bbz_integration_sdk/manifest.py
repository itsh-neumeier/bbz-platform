"""Integration manifest model + JSON-Schema validation.

Every ``integrations/<name>/manifest.json`` is validated against
``schemas/manifest.schema.json`` (MASTER_PROMPT §7).
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib.resources import files
from typing import Any

import jsonschema
from pydantic import BaseModel, Field


class ManifestError(ValueError):
    """Raised when a manifest fails schema or semantic validation."""


class IntegrationManifest(BaseModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    name: str
    version: str
    domain: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    adapter: str
    minimum_core_version: str = "0.0.0"
    config_schema_version: int = 1
    dependencies: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    # Foundation phase: only mock adapters are allowed to be "production" ready.
    mock: bool = False
    description: str = ""


@lru_cache
def _schema() -> dict[str, Any]:
    text = (files("bbz_integration_sdk.schemas") / "manifest.schema.json").read_text("utf-8")
    schema: dict[str, Any] = json.loads(text)
    return schema


def manifest_schema() -> dict[str, Any]:
    return dict(_schema())


def validate_manifest(raw: dict[str, Any]) -> IntegrationManifest:
    try:
        jsonschema.validate(instance=raw, schema=_schema())
    except jsonschema.ValidationError as exc:
        raise ManifestError(f"manifest schema violation: {exc.message}") from exc
    return IntegrationManifest.model_validate(raw)
