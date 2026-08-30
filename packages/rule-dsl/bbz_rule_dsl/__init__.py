"""Safe, restricted rule DSL (ADR-0005 / ADR-0004 / ADR-0010).

Used for:
* EPK OR/XOR branch conditions
* technical trigger-rule conditions

**Hard constraint:** never ``eval``/``exec`` or any dynamic code execution.
Expressions operate over an allowlisted, typed context and a fixed operator set.

``parse`` validates a structured expression against the operator/field
allowlists; :func:`evaluate` is a **total, side-effect-free** predicate over a
typed :class:`Context` — deterministic, never ``eval``, and raising
``RuleDslError`` (never "silently true") on any type mismatch, bad arity,
unknown field/operator or excessive nesting. Covered by unit tests per operator
plus a Hypothesis fuzz suite (E05-01, ADR-0010). The typed context registry
(``ALLOWED_FIELDS`` split by usage) is E05-02.
"""

from bbz_rule_dsl.model import (
    ALLOWED_OPERATORS,
    Context,
    Expr,
    RuleDslError,
    UnknownField,
    evaluate,
    parse,
)

__all__ = [
    "ALLOWED_OPERATORS",
    "Context",
    "Expr",
    "RuleDslError",
    "UnknownField",
    "evaluate",
    "parse",
]

__version__ = "0.0.0"
