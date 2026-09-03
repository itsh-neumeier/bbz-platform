"""Every migration is safe for the previous app version (roadmap E06-10).

A rolling update runs old and new code against the same schema, so a migration
may not break the previous app release. A destructive operation in ``upgrade()``
is only allowed as the **contract** phase of an expand/contract change and must
say so in the module docstring (``expand-contract: contract`` / ``: safe``).
See ``docs/CONVENTIONS.md``.
"""

from __future__ import annotations

import ast
import re
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


def test_uuid_pk_columns_get_a_server_default_in_migrations() -> None:
    """Every ``uuid_pk()`` table (``id`` has ``server_default gen_random_uuid()``
    in the model) must get that default from a migration too — either in the
    migration that ``create_table``s it, or from a later ``ALTER … SET DEFAULT``.
    Otherwise an ``INSERT`` without an explicit id fails only on a
    migration-provisioned DB, never in the ``create_all`` test suite (0054).
    """
    from bbz_core.infra.models import Base

    want: set[str] = set()
    for table in Base.metadata.tables.values():
        col = table.columns.get("id")
        sd = getattr(getattr(col, "server_default", None), "arg", None)
        text = getattr(sd, "text", "") if sd is not None else ""
        if col is not None and "gen_random_uuid" in str(text):
            want.add(table.name)

    sources = {p.name: p.read_text(encoding="utf-8") for p in _MIGRATIONS}

    # migrations that add an id default via ALTER (possibly in a loop over a
    # table tuple) — collect the quoted table names they touch
    altered: set[str] = set()
    for src in sources.values():
        if "ALTER COLUMN id SET DEFAULT" in src:
            altered |= set(re.findall(r'["\']([a-z_]+)["\']', src))

    missing: list[str] = []
    for table in sorted(want):
        # the file that creates the table must itself mention gen_random_uuid()
        creators = [
            src
            for src in sources.values()
            if re.search(rf'create_table\(\s*["\']{re.escape(table)}["\']', src)
        ]
        created_with_default = any("gen_random_uuid" in src for src in creators)
        if not (table in altered or created_with_default):
            missing.append(table)

    assert not missing, (
        "these uuid PKs never receive a gen_random_uuid() default from a "
        f"migration (add ALTER TABLE … ALTER COLUMN id SET DEFAULT): {missing}"
    )
