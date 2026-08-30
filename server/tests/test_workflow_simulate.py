"""In-memory workflow simulation + definition diff (E05-13)."""

from __future__ import annotations

from typing import Any

from bbz_core.domain.workflow import diff_definitions, simulate


def _cond(field: str, value: str) -> dict[str, Any]:
    return {"op": "eq", "args": [{"field": field}, value]}


_AND: dict[str, Any] = {
    "start": "e0",
    "nodes": [
        {"key": "e0", "type": "event"},
        {"key": "as", "type": "connector", "connector": "and", "direction": "split"},
        {"key": "f1", "type": "function", "kind": "manual"},
        {"key": "f2", "type": "function", "kind": "documentation"},
        {"key": "aj", "type": "connector", "connector": "and", "direction": "join"},
        {"key": "e1", "type": "event"},
    ],
    "edges": [
        {"key": "a", "from": "e0", "to": "as"},
        {"key": "b", "from": "as", "to": "f1"},
        {"key": "c", "from": "as", "to": "f2"},
        {"key": "d", "from": "f1", "to": "aj"},
        {"key": "e", "from": "f2", "to": "aj"},
        {"key": "f", "from": "aj", "to": "e1"},
    ],
}

_ALARM: dict[str, Any] = {
    "start": "e0",
    "nodes": [
        {"key": "e0", "type": "event"},
        {
            "key": "cam",
            "type": "function",
            "kind": "integration_action",
            "props": {"capability": "camera.point"},
        },
        {"key": "note", "type": "function", "kind": "notification", "props": {"channel": "ops"}},
        {"key": "e1", "type": "event"},
    ],
    "edges": [
        {"key": "a", "from": "e0", "to": "cam"},
        {"key": "b", "from": "cam", "to": "note"},
        {"key": "c", "from": "note", "to": "e1"},
    ],
}

_XOR: dict[str, Any] = {
    "start": "e0",
    "nodes": [
        {"key": "e0", "type": "event"},
        {"key": "xs", "type": "connector", "connector": "xor", "direction": "split"},
        {"key": "f1", "type": "function", "kind": "manual"},
        {"key": "f2", "type": "function", "kind": "manual"},
        {"key": "xj", "type": "connector", "connector": "xor", "direction": "join"},
        {"key": "e1", "type": "event"},
    ],
    "edges": [
        {"key": "a", "from": "e0", "to": "xs"},
        {"key": "b", "from": "xs", "to": "f1", "condition": _cond("severity", "high")},
        {"key": "c", "from": "xs", "to": "f2", "condition": _cond("severity", "low")},
        {"key": "d", "from": "f1", "to": "xj"},
        {"key": "e", "from": "f2", "to": "xj"},
        {"key": "f", "from": "xj", "to": "e1"},
    ],
}

_TIMER: dict[str, Any] = {
    "start": "e0",
    "nodes": [
        {"key": "e0", "type": "event"},
        {"key": "w", "type": "function", "kind": "timer", "props": {"duration_seconds": 300}},
        {"key": "e1", "type": "event"},
    ],
    "edges": [
        {"key": "a", "from": "e0", "to": "w"},
        {"key": "b", "from": "w", "to": "e1"},
    ],
}


def test_and_graph_runs_to_completion_auto_completing_operator_steps() -> None:
    r = simulate(_AND)
    assert r.status == "completed"
    assert {s["node_key"] for s in r.steps} == {"f1", "f2"}
    assert r.outbox_dry_run == []
    assert "aj" in r.visited_nodes  # both branches reached the join
    assert r.active_nodes == []


def test_alarm_workflow_records_dry_run_actions_and_enqueues_nothing() -> None:
    r = simulate(_ALARM)
    assert r.status == "completed"
    kinds = {row["action_type"] for row in r.outbox_dry_run}
    assert kinds == {"integration", "notify"}
    for row in r.outbox_dry_run:
        assert row["dedupe_key"].startswith("workflow-step:")
    # dry-run only — the report is the sole artefact, nothing is enqueued
    assert [s["outcome"] for s in r.steps] == ["dispatched (dry-run)", "dispatched (dry-run)"]


def test_xor_takes_the_matching_branch_from_context() -> None:
    r = simulate(_XOR, context={"severity": "low"})
    assert r.status == "completed"
    assert [d["chosen_branches"] for d in r.decisions] == [["c"]]
    assert {s["node_key"] for s in r.steps} == {"f2"}


def test_xor_without_a_resolution_reports_a_pending_decision() -> None:
    r = simulate(_XOR, context={"severity": "medium"})
    assert r.status == "running"
    assert r.pending_decisions == ["xs"]
    assert r.active_nodes == ["xs"]


def test_xor_uses_a_supplied_operator_decision() -> None:
    r = simulate(_XOR, context={"severity": "medium"}, decisions={"xs": ["b"]})
    assert r.status == "completed"
    assert {s["node_key"] for s in r.steps} == {"f1"}


def test_timer_is_fast_forwarded() -> None:
    r = simulate(_TIMER)
    assert r.status == "completed"
    assert r.steps[0]["outcome"] == "waited 300s (fast-forward)"


def test_diff_reports_structural_changes() -> None:
    v1 = {
        "start": "e0",
        "nodes": [
            {"key": "e0", "type": "event"},
            {"key": "f", "type": "function", "kind": "manual"},
        ],
        "edges": [{"key": "a", "from": "e0", "to": "f"}],
    }
    v2 = {
        "start": "e0",
        "nodes": [
            {"key": "e0", "type": "event"},
            {"key": "f", "type": "function", "kind": "confirmation"},
            {"key": "g", "type": "function", "kind": "manual"},
        ],
        "edges": [{"key": "a", "from": "e0", "to": "f"}, {"key": "b", "from": "f", "to": "g"}],
    }
    d = diff_definitions(v1, v2)
    assert d["nodes_added"] == ["g"]
    assert d["nodes_changed"] == ["f"]
    assert d["edges_added"] == ["b"]
    assert d["nodes_removed"] == [] and d["start_changed"] is False


def test_diff_against_nothing_is_all_additions() -> None:
    d = diff_definitions(
        None, {"start": "e0", "nodes": [{"key": "e0", "type": "event"}], "edges": []}
    )
    assert d["nodes_added"] == ["e0"]
