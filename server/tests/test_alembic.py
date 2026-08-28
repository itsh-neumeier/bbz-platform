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
