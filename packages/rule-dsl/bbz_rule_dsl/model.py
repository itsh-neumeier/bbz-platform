from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Final

ALLOWED_OPERATORS: Final[frozenset[str]] = frozenset(
    {"eq", "ne", "in", "not_in", "lt", "lte", "gt", "gte", "and", "or", "not", "exists"}
)

# Allowlisted context fields for trigger-rule / condition evaluation
# (TECHNICAL_TRIGGERS.md + WORKFLOW_EPK.md). Extended per phase via ADR only.
ALLOWED_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "provider",
        "signal_type",
        "calling_number",
        "called_number",
        "cti_route_point",
        "technical_endpoint_id",
        "external_source_id",
        "workplace",
        "site",
        "station",
        "alarm_type",
        "alarm_subtype",
        "severity",
        "call_direction",
        "call_state",
    }
)


class RuleDslError(ValueError):
    """Base error for the rule DSL."""


class UnknownField(RuleDslError):
    def __init__(self, name: str) -> None:
        super().__init__(f"field not allowlisted in rule DSL: {name!r}")
        self.name = name


@dataclass(frozen=True)
class Context:
    """Typed, read-only evaluation context. Only allowlisted keys are accepted."""

    values: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        unknown = set(self.values) - ALLOWED_FIELDS
        if unknown:
            raise UnknownField(", ".join(sorted(unknown)))

    def get(self, name: str) -> Any:
        if name not in ALLOWED_FIELDS:
            raise UnknownField(name)
        return self.values.get(name)


@dataclass(frozen=True)
class Expr:
    """A parsed, validated expression node.

    Shape: ``{"op": <operator>, "args": [...]}`` where a leaf field reference is
    ``{"field": "<name>"}`` and a literal is any JSON scalar/list.
    """

    op: str
    args: tuple[Any, ...]


def parse(tree: dict[str, Any]) -> Expr:
    """Validate a structured expression (no string parsing, no code).

    Raises ``RuleDslError`` for unknown operators or non-allowlisted fields.
    """
    if not isinstance(tree, dict) or "op" not in tree:
        raise RuleDslError("expression must be an object with an 'op' key")
    op = tree["op"]
    if op not in ALLOWED_OPERATORS:
        raise RuleDslError(f"operator not allowed: {op!r}")
    raw_args = tree.get("args", [])
    if not isinstance(raw_args, list):
        raise RuleDslError("'args' must be a list")

    parsed_args: list[Any] = []
    for arg in raw_args:
        if isinstance(arg, dict) and "op" in arg:
            parsed_args.append(parse(arg))
        elif isinstance(arg, dict) and "field" in arg:
            name = arg["field"]
            if name not in ALLOWED_FIELDS:
                raise UnknownField(str(name))
            parsed_args.append(arg)
        else:
            parsed_args.append(arg)
    return Expr(op=op, args=tuple(parsed_args))


def evaluate(expr: Expr, context: Context) -> bool:
    """Not implemented in the foundation phase.

    Implemented with the trigger/workflow engines (Phase 1+), together with a
    fuzz-test suite. Deliberately raises rather than returning a possibly-unsafe
    default.
    """
    raise NotImplementedError(
        "rule DSL evaluation arrives with the trigger/workflow engine (ADR-0010)"
    )
