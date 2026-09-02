"""E23-08: every self-built image runs as a non-root user."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_MOD = _ROOT / "tools" / "security" / "check_dockerfiles.py"

_spec = importlib.util.spec_from_file_location("check_dockerfiles", _MOD)
assert _spec and _spec.loader
cd = importlib.util.module_from_spec(_spec)
sys.modules["check_dockerfiles"] = cd
_spec.loader.exec_module(cd)


def test_the_repo_has_no_root_dockerfiles() -> None:
    assert cd.violations() == []


def test_the_api_dockerfile_sets_a_non_root_user() -> None:
    text = (_ROOT / "server" / "Dockerfile").read_text(encoding="utf-8")
    user = cd.effective_user(text)
    assert user and user.lower() not in cd._ROOT_USERS


def test_a_multistage_file_needs_user_in_the_runtime_stage() -> None:
    no_user = (
        'FROM python:3.13-slim AS deps\nRUN pip install x\n\nFROM python:3.13-slim\nCMD ["x"]\n'
    )
    assert cd.effective_user(no_user) is None

    deps_only = (
        'FROM python:3.13-slim AS deps\nUSER app\n\nFROM python:3.13-slim AS runtime\nCMD ["x"]\n'
    )
    assert cd.effective_user(deps_only) is None  # USER didn't carry into runtime

    ok = 'FROM python:3.13-slim AS runtime\nRUN useradd app\nUSER app\nCMD ["x"]\n'
    assert cd.effective_user(ok) == "app"


def test_explicit_root_is_flagged(tmp_path: Path) -> None:
    (tmp_path / "Dockerfile").write_text('FROM alpine\nUSER root\nCMD ["sh"]\n', encoding="utf-8")
    problems = cd.violations(tmp_path)
    assert problems and "must be non-root" in problems[0]
