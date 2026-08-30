"""Typed context registries for the rule DSL (E05-02, ADR-0010).

Field references resolve only against an allowlisted, **typed** context. There
are two separate contexts — one for EPK workflow branch conditions, one for
technical trigger-rule conditions — so a workflow condition can never read a
trigger-only field and vice versa. New fields per feature area are added here
via an ADR touch, never ad hoc.

:meth:`ContextSchema.validate` runs at *publish* time: an unknown field or a
type-incompatible operator (``lt`` on a string, comparing a number field to a
string literal, ``in`` against a non-list) fails then, not at runtime.
"""

from __future__ import annotations

import enum
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from bbz_rule_dsl.model import Expr, RuleDslError, UnknownField, parse

_ORDER_OPS = frozenset({"lt", "lte", "gt", "gte"})
_EQ_OPS = frozenset({"eq", "ne"})
_MEMBER_OPS = frozenset({"in", "not_in"})
_BOOL_OPS = frozenset({"and", "or", "not"})


class FieldType(enum.StrEnum):
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    DATETIME = "datetime"  # ISO-8601 string
    LIST = "list"


_ORDERABLE = frozenset({FieldType.NUMBER, FieldType.DATETIME})


def _is_field_ref(arg: Any) -> bool:
    return isinstance(arg, dict) and "field" in arg


def _literal_matches(ft: FieldType, value: Any) -> bool:
    match ft:
        case FieldType.STRING | FieldType.DATETIME:
            return isinstance(value, str)
        case FieldType.NUMBER:
            return isinstance(value, int | float) and not isinstance(value, bool)
        case FieldType.BOOLEAN:
            return isinstance(value, bool)
        case FieldType.LIST:
            return isinstance(value, list)


@dataclass(frozen=True)
class ContextSchema:
    name: str
    fields: Mapping[str, FieldType]

    def field_type(self, field: str) -> FieldType:
        try:
            return self.fields[field]
        except KeyError as exc:
            raise UnknownField(f"{field!r} (context {self.name!r})") from exc

    def validate(self, expr: Expr | dict[str, Any]) -> None:
        """Raise :class:`RuleDslError` if ``expr`` is not valid for this context."""
        node = expr if isinstance(expr, Expr) else parse(expr)
        self._check(node)

    # -- internals ---------------------------------------------------------------
    def _operand_type(self, arg: Any) -> FieldType | None:
        if isinstance(arg, Expr):
            return FieldType.BOOLEAN  # a nested predicate is a boolean
        if _is_field_ref(arg):
            return self.field_type(str(arg["field"]))
        return None  # a bare literal — type inferred at the call site

    def _check(self, node: Expr) -> None:
        op, args = node.op, node.args

        if op in _BOOL_OPS:
            for arg in args:
                if isinstance(arg, Expr):
                    self._check(arg)
                elif _is_field_ref(arg):
                    self.field_type(str(arg["field"]))  # existence only
            return

        if op == "exists":
            if not (len(args) == 1 and _is_field_ref(args[0])):
                raise RuleDslError("'exists' takes a single field reference")
            self.field_type(str(args[0]["field"]))
            return

        if len(args) != 2:
            raise RuleDslError(f"{op!r} takes exactly 2 arguments")
        left, right = args
        lt, rt = self._operand_type(left), self._operand_type(right)

        if op in _ORDER_OPS:
            for side in (lt, rt):
                if side is not None and side not in _ORDERABLE:
                    raise RuleDslError(
                        f"type mismatch: {op!r} needs orderable operands, got {side.value}"
                    )
            self._check_literal(lt, right)
            self._check_literal(rt, left)
        elif op in _EQ_OPS:
            self._check_literal(lt, right)
            self._check_literal(rt, left)
        elif op in _MEMBER_OPS:
            if rt is None and not isinstance(right, list):
                raise RuleDslError(f"{op!r} needs a list on the right, got a scalar literal")
            if rt is not None and rt is not FieldType.LIST:
                raise RuleDslError(f"{op!r} needs a list on the right, got {rt.value}")
            if lt is not None and isinstance(right, list):
                for item in right:
                    if not _literal_matches(lt, item):
                        raise RuleDslError(f"type mismatch: list item {item!r} is not {lt.value}")

    def _check_literal(self, field_type: FieldType | None, other: Any) -> None:
        if field_type is None or isinstance(other, Expr) or _is_field_ref(other):
            return
        if not _literal_matches(field_type, other):
            raise RuleDslError(
                f"type mismatch: {other!r} is not compatible with a {field_type.value} field"
            )


TRIGGER_CONTEXT = ContextSchema(
    "trigger",
    {
        "provider": FieldType.STRING,
        "signal_type": FieldType.STRING,
        "calling_number": FieldType.STRING,
        "called_number": FieldType.STRING,
        "cti_route_point": FieldType.STRING,
        "technical_endpoint_id": FieldType.STRING,
        "external_source_id": FieldType.STRING,
        "workplace": FieldType.STRING,
        "site": FieldType.STRING,
        "station": FieldType.STRING,
        "alarm_type": FieldType.STRING,
        "alarm_subtype": FieldType.STRING,
        "severity": FieldType.NUMBER,
        "call_direction": FieldType.STRING,
        "call_state": FieldType.STRING,
    },
)

WORKFLOW_CONTEXT = ContextSchema(
    "workflow",
    {
        "event_priority": FieldType.STRING,
        "event_status": FieldType.STRING,
        "event_source": FieldType.STRING,
        "event_bbz_id": FieldType.STRING,
        "event_workplace_id": FieldType.STRING,
        "branch_key": FieldType.STRING,
        "step_completed_count": FieldType.NUMBER,
        "operator_confirmed": FieldType.BOOLEAN,
    },
)
