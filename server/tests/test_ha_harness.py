"""The HA failure-scenario harness is well-formed (roadmap E06-11).

The scenarios cannot run here (they need a real Docker host + Patroni), but CI
can guard that every scenario exists, is valid POSIX shell, ends in a
pass/fail assertion, and that the split-brain check is applied.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml

_HA = Path(__file__).resolve().parents[2] / "deploy" / "ha-test"
_SCENARIOS = [
    "srv01-down",
    "srv02-down",
    "db-primary-loss",
    "net-isolation",
    "witness-down",
    "client-reconnect",
    "recovery",
]
_SPLIT_BRAIN = {"db-primary-loss", "net-isolation", "witness-down", "recovery", "srv01-down"}


def test_all_seven_scenarios_are_present() -> None:
    have = sorted(p.stem for p in (_HA / "scenarios").glob("*.sh"))
    assert have == sorted(_SCENARIOS)


@pytest.mark.parametrize("name", _SCENARIOS)
def test_scenario_is_valid_shell_and_asserts_something(name: str) -> None:
    path = _HA / "scenarios" / f"{name}.sh"
    text = path.read_text(encoding="utf-8")
    assert subprocess.run(["sh", "-n", str(path)]).returncode == 0
    assert '. "$(dirname -- "$0")/../lib.sh"' in text
    assert "pass " in text and ("fail " in text or "|| fail" in text)


@pytest.mark.parametrize("name", sorted(_SPLIT_BRAIN))
def test_split_brain_scenarios_assert_a_single_primary(name: str) -> None:
    text = (_HA / "scenarios" / f"{name}.sh").read_text(encoding="utf-8")
    assert "assert_single_primary" in text


def test_run_and_setup_and_lib_are_valid_shell() -> None:
    for name in ("run.sh", "setup.sh", "lib.sh"):
        assert subprocess.run(["sh", "-n", str(_HA / name)]).returncode == 0


def test_compose_declares_the_mini_cluster() -> None:
    c = yaml.safe_load((_HA / "compose.yml").read_text(encoding="utf-8"))
    assert c["name"] == "bbz-ha-test"
    services = set(c["services"])
    assert {"api1", "api2", "pg1", "pg2", "pgha", "etcd1", "etcd2", "etcd3", "lb"} <= services


def test_nightly_workflow_runs_the_harness_and_is_not_a_pr_gate() -> None:
    path = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ha-nightly.yml"
    wf = yaml.safe_load(path.read_text(encoding="utf-8"))
    triggers = wf[True] if True in wf else wf.get("on", {})
    assert "schedule" in triggers and "pull_request" not in triggers
    job = wf["jobs"]["ha-scenarios"]
    assert job["continue-on-error"] is True
    assert any("run.sh" in s.get("run", "") for s in job["steps"])
