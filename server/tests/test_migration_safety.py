"""Every migration is safe for the previous app version (roadmap E06-10).

A rolling update runs old and new code against the same schema, so a migration
may not break the previous app release. A destructive operation in ``upgrade()``
is only allowed as the **contract** phase of an expand/contract change and must
say so in the module docstring (``expand-contract: contract`` / ``: safe``).
See ``docs/CONVENTIONS.md``.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

_VERSIONS = Path(__file__).resolve().parents[1] / "alembic" / "versions"

_DESTRUCTIVE_OPS = {"drop_column", "drop_table", "drop_constraint"}
_DESTRUCTIVE_SQL = (
    "drop column",
    "drop table",
    "set not null",
    "rename column",
    "rename to",
    "rename constraint",
)
_MARKERS = ("expand-contract: contract", "expand-contract: safe")

_MIGRATIONS = sorted(p for p in _VERSIONS.glob("*.py") if p.name != "__init__.py")


def _upgrade_node(tree: ast.Module) -> ast.FunctionDef:
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "upgrade":
            return node
    raise AssertionError("no upgrade() function")


def _destructive_reasons(fn: ast.FunctionDef) -> list[str]:
    reasons: list[str] = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
        if name in _DESTRUCTIVE_OPS:
            reasons.append(f"op.{name}(...)")
        elif name == "alter_column":
            for kw in node.keywords:
                is_false = isinstance(kw.value, ast.Constant) and kw.value.value is False
                if kw.arg == "nullable" and is_false:
                    reasons.append("op.alter_column(nullable=False)")
        elif name == "execute":
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    low = arg.value.lower()
                    reasons += [f"execute({s!r})" for s in _DESTRUCTIVE_SQL if s in low]
    return reasons


@pytest.mark.parametrize("path", _MIGRATIONS, ids=lambda p: p.stem)
def test_migration_upgrade_is_backward_compatible(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    reasons = _destructive_reasons(_upgrade_node(ast.parse(source)))
    if not reasons:
        return
    assert any(m in source for m in _MARKERS), (
        f"{path.name} has a destructive upgrade ({', '.join(sorted(set(reasons)))}) "
        f"but no expand/contract marker — see docs/CONVENTIONS.md"
    )


def test_revision_id_matches_the_filename() -> None:
    for path in _MIGRATIONS:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        rev = next(
            (
                node.value.value
                for node in tree.body
                if isinstance(node, ast.AnnAssign)
                and isinstance(node.target, ast.Name)
                and node.target.id == "revision"
                and isinstance(node.value, ast.Constant)
            ),
            None,
        )
        assert rev == path.stem, f"{path.name}: revision {rev!r} != filename stem"
