"""Safe, restricted rule DSL (ADR-0005 / ADR-0004 / ADR-0010).

Used for:
* EPK OR/XOR branch conditions
* technical trigger-rule conditions

**Hard constraint:** never ``eval``/``exec`` or any dynamic code execution.
Expressions operate over an allowlisted, typed context and a fixed operator set.

Foundation phase status: the public surface (``parse``, ``Expr``, ``Context``)
is defined and a whitelist of field names / operators is fixed. The evaluator is
intentionally not implemented yet — :func:`evaluate` raises
``NotImplementedError``. The full parser + evaluator + fuzz tests land with the
workflow/trigger engines. This keeps the contract stable without shipping an
unsafe stub.
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
