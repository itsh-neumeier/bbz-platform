"""Alembic wiring checks that do not need a live database.

Full upgrade/downgrade/upgrade against real PostgreSQL runs in CI's
integration job (docker compose) and in the migration gate before every release.
"""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

_SERVER_DIR = Path(__file__).resolve().parents[1]


def _script_dir() -> ScriptDirectory:
    cfg = Config(str(_SERVER_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(_SERVER_DIR / "alembic"))
    return ScriptDirectory.from_config(cfg)


def test_single_head() -> None:
    assert len(_script_dir().get_heads()) == 1, "migration history must not fork"


def test_baseline_is_reversible() -> None:
    rev = _script_dir().get_revision("0001_baseline")
    src = Path(rev.module.__file__).read_text(encoding="utf-8")
    # downgrade must actually do something (not a bare pass)
    body = src.split("def downgrade()", 1)[1]
    assert "DROP EXTENSION" in body


def test_every_downgrade_is_nontrivial() -> None:
    """No migration may ship a bare ``pass`` downgrade (§21 rolling-update safety)."""
    for rev in _script_dir().walk_revisions():
        src = Path(rev.module.__file__).read_text(encoding="utf-8")
        body = src.split("def downgrade()", 1)[1]
        meaningful = [
            ln.strip()
            for ln in body.splitlines()
            if ln.strip() and not ln.strip().startswith(("#", '"', "'"))
        ]
        assert meaningful and meaningful != ["pass"], f"{rev.revision}: empty downgrade"


def test_identity_migration_drops_its_tables() -> None:
    rev = _script_dir().get_revision("0002_identity")
    body = Path(rev.module.__file__).read_text(encoding="utf-8").split("def downgrade()", 1)[1]
    for tbl in ("users", "auth_identities", "user_presence"):
        assert f'drop_table("{tbl}")' in body
