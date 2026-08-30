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


_MAX_DEPTH: Final[int] = 64

_BINARY_CMP: Final[frozenset[str]] = frozenset({"eq", "ne", "lt", "lte", "gt", "gte"})
_MEMBERSHIP: Final[frozenset[str]] = frozenset({"in", "not_in"})


def _is_field_ref(arg: Any) -> bool:
    return isinstance(arg, dict) and "field" in arg


def _value(arg: Any, context: Context, depth: int) -> Any:
    """Resolve an operand to a concrete value (field -> context, literal -> itself)."""
    if isinstance(arg, Expr):
        return _eval(arg, context, depth + 1)
    if _is_field_ref(arg):
        return context.get(str(arg["field"]))
    if isinstance(arg, dict):
        raise RuleDslError(f"unexpected operand shape: {sorted(arg)!r}")
    return arg


def _truthy(arg: Any, context: Context, depth: int) -> bool:
    if isinstance(arg, Expr):
        return _eval(arg, context, depth + 1)
    if _is_field_ref(arg):
        return bool(context.get(str(arg["field"])))
    return bool(arg)


def _require_arity(
    op: str, args: tuple[Any, ...], *, n: int | None = None, at_least: int | None = None
) -> None:
    if n is not None and len(args) != n:
        raise RuleDslError(f"{op!r} takes exactly {n} argument(s), got {len(args)}")
    if at_least is not None and len(args) < at_least:
        raise RuleDslError(f"{op!r} takes at least {at_least} argument(s), got {len(args)}")


def _compare(op: str, left: Any, right: Any) -> bool:
    if op == "eq":
        return bool(left == right)
    if op == "ne":
        return bool(left != right)
    try:
        if op == "lt":
            return bool(left < right)
        if op == "lte":
            return bool(left <= right)
        if op == "gt":
            return bool(left > right)
        return bool(left >= right)  # gte
    except TypeError as exc:
        lt_name, rt_name = type(left).__name__, type(right).__name__
        raise RuleDslError(
            f"type mismatch: cannot apply {op!r} to {lt_name} and {rt_name}"
        ) from exc


def _eval(expr: Expr, context: Context, depth: int) -> bool:
    if depth > _MAX_DEPTH:
        raise RuleDslError("expression nesting exceeds the maximum depth")
    op, args = expr.op, expr.args

    if op == "and":
        _require_arity(op, args, at_least=1)
        return all(_truthy(a, context, depth) for a in args)
    if op == "or":
        _require_arity(op, args, at_least=1)
        return any(_truthy(a, context, depth) for a in args)
    if op == "not":
        _require_arity(op, args, n=1)
        return not _truthy(args[0], context, depth)

    if op == "exists":
        _require_arity(op, args, n=1)
        if not _is_field_ref(args[0]):
            raise RuleDslError("'exists' takes a single field reference")
        return context.get(str(args[0]["field"])) is not None

    if op in _BINARY_CMP:
        _require_arity(op, args, n=2)
        return _compare(op, _value(args[0], context, depth), _value(args[1], context, depth))

    if op in _MEMBERSHIP:
        _require_arity(op, args, n=2)
        needle = _value(args[0], context, depth)
        haystack = _value(args[1], context, depth)
        if not isinstance(haystack, (list, tuple, set, frozenset, str)):
            raise RuleDslError(
                f"type mismatch: right operand of {op!r} must be a collection, "
                f"got {type(haystack).__name__}"
            )
        try:
            found = needle in haystack
        except TypeError as exc:
            raise RuleDslError(
                f"type mismatch: {type(needle).__name__} not comparable with the "
                f"{type(haystack).__name__} operand of {op!r}"
            ) from exc
        return found if op == "in" else not found

    raise RuleDslError(f"operator not allowed: {op!r}")  # unreachable after parse()


def evaluate(expr: Expr, context: Context) -> bool:
    """Evaluate a parsed expression against a context — total, side-effect-free.

    Deterministic: the same ``(expr, context)`` always yields the same boolean.
    Any type mismatch, wrong arity, unknown field/operator or excessive nesting
    raises :class:`RuleDslError` — it never silently returns ``True``.
    """
    if not isinstance(expr, Expr):
        raise RuleDslError("evaluate() expects a parsed Expr (call parse() first)")
    return _eval(expr, context, 0)
