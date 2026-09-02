"""E23-07: the vulnerability-scan exception policy gate."""

from __future__ import annotations

import datetime as _dt
import importlib.util
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_MOD = _ROOT / "tools" / "security" / "check_scan_exceptions.py"

_spec = importlib.util.spec_from_file_location("check_scan_exceptions", _MOD)
assert _spec and _spec.loader
cse = importlib.util.module_from_spec(_spec)
sys.modules["check_scan_exceptions"] = cse
_spec.loader.exec_module(cse)

_TODAY = _dt.date(2026, 6, 1)


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "scan-exceptions.toml"
    p.write_text(body, encoding="utf-8")
    return p


def test_the_checked_in_file_is_clean() -> None:
    # the real deploy/security/scan-exceptions.toml must always pass
    assert cse.validate(cse.load()) == []


def test_an_empty_or_missing_file_is_fine(tmp_path: Path) -> None:
    assert cse.validate(cse.load(tmp_path / "nope.toml")) == []
    assert cse.validate(cse.load(_write(tmp_path, "# just a comment\n"))) == []


def test_a_well_formed_future_exception_passes(tmp_path: Path) -> None:
    body = '[[pip_audit]]\nid = "GHSA-aaaa-bbbb-cccc"\nexpires = "2026-07-15"\nreason = "no fix"\n'
    assert cse.validate(cse.load(_write(tmp_path, body)), today=_TODAY) == []


def test_an_expired_exception_fails(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        '[[trivy]]\nid = "CVE-2026-1"\nexpires = "2026-05-01"\nreason = "x"\n',
    )
    problems = cse.validate(cse.load(path), today=_TODAY)
    assert problems and "expired" in problems[0]


def test_missing_reason_or_bad_date_fails(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        '[[pip_audit]]\nid = "GHSA-x"\nexpires = "2026-07-01"\n\n'
        '[[pip_audit]]\nid = "GHSA-y"\nexpires = "soon"\nreason = "r"\n',
    )
    problems = cse.validate(cse.load(path), today=_TODAY)
    assert any("missing `reason`" in p for p in problems)
    assert any("ISO" in p for p in problems)


def test_an_exception_more_than_90_days_out_fails(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        '[[trivy]]\nid = "CVE-2026-2"\nexpires = "2026-12-31"\nreason = "r"\n',
    )
    problems = cse.validate(cse.load(path), today=_TODAY)
    assert problems and "stopgap" in problems[0]


def test_it_emits_scanner_flags(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = _write(
        tmp_path,
        '[[pip_audit]]\nid = "GHSA-1"\nexpires = "2026-07-01"\nreason = "r"\n'
        '[[pip_audit]]\nid = "GHSA-2"\nexpires = "2026-07-01"\nreason = "r"\n'
        '[[trivy]]\nid = "CVE-9"\nexpires = "2026-07-01"\nreason = "base image"\n',
    )
    cse.main(["--path", str(path), "--pip-audit-args"])
    assert capsys.readouterr().out.strip() == "--ignore-vuln GHSA-1 --ignore-vuln GHSA-2"

    cse.main(["--path", str(path), "--trivyignore"])
    out = capsys.readouterr().out
    assert "CVE-9" in out and "# base image (expires 2026-07-01)" in out


def test_check_mode_exit_code(tmp_path: Path) -> None:
    ok = _write(tmp_path, "")
    assert cse.main(["--path", str(ok), "--check"]) == 0
    bad = _write(tmp_path, '[[trivy]]\nid = "CVE-x"\nexpires = "2000-01-01"\nreason = "r"\n')
    assert cse.main(["--path", str(bad), "--check"]) == 1
