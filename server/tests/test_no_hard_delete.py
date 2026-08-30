"""Contract: the event record and the audit trail are never hard-deleted (E20-07).

See ``docs/domain/retention-policy.md``. This test fails if application code or a
migration gains a delete path against one of the protected tables, or if the
DB-level guard triggers stop being created.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]
_BBZ_CORE = _ROOT / "bbz_core"
_VERSIONS = _ROOT / "alembic" / "versions"

# table name -> ORM model class name
_PROTECTED = {
    "events": "Event",
    "event_status_history": "EventStatusHistory",
    "event_notes": "EventNote",
    "domain_events": "DomainEvent",
    "audit_events": "AuditEvent",
}
_MODELS = set(_PROTECTED.values())
_DELETE_FROM = re.compile(r"delete\s+from\s+(" + "|".join(_PROTECTED) + r")\b", re.IGNORECASE)


def _py_files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*.py") if "__pycache__" not in p.parts]


def test_no_app_code_deletes_a_protected_table() -> None:
    offenders: list[str] = []
    for path in _py_files(_BBZ_CORE):
        source = path.read_text(encoding="utf-8")
        rel = path.relative_to(_ROOT)

        for m in _DELETE_FROM.finditer(source):
            offenders.append(f"{rel}: raw SQL 'DELETE FROM {m.group(1)}'")

        for node in ast.walk(ast.parse(source)):
            if not isinstance(node, ast.Call):
                continue
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            # sqlalchemy delete(Model) / session.delete(obj-of-protected-model)
            if name == "delete" and node.args:
                arg = node.args[0]
                if isinstance(arg, ast.Name) and arg.id in _MODELS:
                    offenders.append(f"{rel}:{node.lineno}: delete({arg.id})")

    assert not offenders, "hard-delete path against a protected table:\n" + "\n".join(offenders)


@pytest.mark.parametrize(
    "path",
    sorted(p for p in _VERSIONS.glob("*.py") if p.name != "__init__.py"),
    ids=lambda p: p.stem,
)
def test_no_migration_upgrade_deletes_a_protected_table(path: Path) -> None:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    upgrade = next(
        (n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "upgrade"), None
    )
    assert upgrade is not None, f"{path.name}: no upgrade()"

    bad: list[str] = []
    for node in ast.walk(upgrade):
        if not isinstance(node, ast.Call):
            continue
        fn = node.func
        name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
        if name == "drop_table" and node.args:
            a = node.args[0]
            if isinstance(a, ast.Constant) and a.value in _PROTECTED:
                bad.append(f"drop_table({a.value!r})")
        if name == "execute":
            for a in node.args:
                if isinstance(a, ast.Constant) and isinstance(a.value, str):
                    for m in _DELETE_FROM.finditer(a.value):
                        bad.append(f"execute(... DELETE FROM {m.group(1)} ...)")
    assert not bad, f"{path.name} upgrade() deletes a protected table: {bad}"


def _migration(stem: str) -> str:
    return (_VERSIONS / f"{stem}.py").read_text(encoding="utf-8")


def test_append_only_triggers_are_still_created() -> None:
    m0016 = _migration("0016_audit_immutability")
    assert "CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table} " in m0016
    assert '_TABLES = ("audit_events", "domain_events")' in m0016


def test_events_delete_guard_trigger_is_created() -> None:
    m = _migration("0023_events_delete_guard")
    assert "CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table} " in m
    assert '_TABLES = ("events", "event_status_history", "event_notes")' in m


def test_retention_policy_doc_exists_and_names_the_guards() -> None:
    doc = (_ROOT.parent / "docs" / "domain" / "retention-policy.md").read_text(encoding="utf-8")
    for table in _PROTECTED:
        assert table in doc, f"retention-policy.md does not mention {table}"
    assert "test_no_hard_delete.py" in doc
