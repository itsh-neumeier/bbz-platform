from __future__ import annotations

import json
from importlib.resources import files
from typing import Any

import jsonschema


def list_schemas() -> list[str]:
    root = files("bbz_event_schemas.schemas")
    return sorted(p.name for p in root.iterdir() if p.name.endswith(".json"))


def load_schema(name: str) -> dict[str, Any]:
    if not name.endswith(".json"):
        name = f"{name}.json"
    text = (files("bbz_event_schemas.schemas") / name).read_text("utf-8")
    schema: dict[str, Any] = json.loads(text)
    # Fail fast if a shipped schema is itself invalid.
    jsonschema.Draft202012Validator.check_schema(schema)
    return schema
