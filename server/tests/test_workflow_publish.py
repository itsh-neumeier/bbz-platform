"""Publish validation: golden graph passes, one negative per rule (E05-06)."""

from __future__ import annotations

import copy
from typing import Any

import pytest

from bbz_core.domain.workflow import validate_publishable

# A sound EPK graph: event start -> xor split (conditioned) -> two functions ->
# xor join -> or split (labelled) -> two notifications -> or join -> end event.
GOLDEN: dict[str, Any] = {
    "start": "e_start",
    "nodes": [
        {"key": "e_start", "type": "event", "label": "BMA-Anruf"},
        {"key": "x_s", "type": "connector", "connector": "xor", "direction": "split"},
        {"key": "f_confirm", "type": "function", "kind": "confirmation"},
        {"key": "f_doc", "type": "function", "kind": "documentation"},
        {"key": "x_j", "type": "connector", "connector": "xor", "direction": "join"},
        {"key": "o_s", "type": "connector", "connector": "or", "direction": "split"},
        {
            "key": "f_notify_fw",
            "type": "function",
            "kind": "notification",
            "props": {"channel": "sms"},
        },
        {
            "key": "f_act",
            "type": "function",
            "kind": "integration_action",
            "props": {"capability": "door.open"},
        },
        {"key": "o_j", "type": "connector", "connector": "or", "direction": "join"},
        {"key": "e_end", "type": "event", "label": "Abgeschlossen"},
    ],
    "edges": [
        {"key": "a", "from": "e_start", "to": "x_s"},
        {
            "key": "b",
            "from": "x_s",
            "to": "f_confirm",
            "condition": {"op": "eq", "args": [{"field": "event_priority"}, "critical"]},
        },
        {"key": "c", "from": "x_s", "to": "f_doc"},
        {"key": "d", "from": "f_confirm", "to": "x_j"},
        {"key": "e", "from": "f_doc", "to": "x_j"},
        {"key": "f", "from": "x_j", "to": "o_s"},
        {"key": "g", "from": "o_s", "to": "f_notify_fw", "branch": "fw"},
        {"key": "h", "from": "o_s", "to": "f_act", "branch": "door"},
        {"key": "i", "from": "f_notify_fw", "to": "o_j"},
        {"key": "j", "from": "f_act", "to": "o_j"},
        {"key": "k", "from": "o_j", "to": "e_end"},
    ],
}


def _codes(definition: dict[str, Any], **kw: Any) -> set[str]:
    return {i.code for i in validate_publishable(definition, **kw)}


def test_golden_graph_is_publishable() -> None:
    assert validate_publishable(GOLDEN, known_capabilities={"door.open"}) == []


def _mut(fn: Any) -> dict[str, Any]:
    g = copy.deepcopy(GOLDEN)
    fn(g)
    return g


@pytest.mark.parametrize(
    ("mutate", "expected_code"),
    [
        (lambda g: g.update(start="x_s"), "start_not_event"),
        (
            lambda g: g["edges"].append({"key": "z", "from": "e_end", "to": "e_start"}),
            "start_has_predecessor",
        ),
        (
            lambda g: g["nodes"].append({"key": "lonely", "type": "event"}),
            "orphan",
        ),
        (
            lambda g: g["edges"].append({"key": "c2", "from": "f_confirm", "to": "e_end"}),
            "branch_without_connector",
        ),
        (lambda g: _drop_edge(g, "c"), "split_cardinality"),
        (lambda g: _drop_edge(g, "e"), "join_cardinality"),
        (lambda g: _clear_condition(g, "b"), "xor_unresolvable"),
        (lambda g: _clear_branch(g, "g"), "or_untrackable"),
        (lambda g: _drop_prop(g, "f_notify_fw", "channel"), "missing_prop"),
        (lambda g: _set_capability(g, "nope"), "unknown_capability"),
        (lambda g: _make_cycle(g), "unbounded_loop"),
    ],
)
def test_each_rule_has_a_negative_case(mutate: Any, expected_code: str) -> None:
    codes = _codes(_mut(mutate), known_capabilities={"door.open"})
    assert expected_code in codes, codes


def test_structurally_broken_graph_returns_one_structure_issue() -> None:
    issues = validate_publishable({"start": "x", "nodes": [], "edges": []})
    assert [i.code for i in issues] == ["structure"]


def test_cycle_with_explicit_reentry_bound_is_not_flagged_as_unbounded() -> None:
    def rewire(g: dict[str, Any]) -> None:
        _find(g, "x_s")["props"] = {"reentry": {"max": 3}}
        g["edges"].append({"key": "loop", "from": "f_doc", "to": "x_s"})

    assert "unbounded_loop" not in _codes(_mut(rewire), known_capabilities={"door.open"})


def test_no_reachable_end_is_flagged() -> None:
    def rewire(g: dict[str, Any]) -> None:
        g["nodes"].remove(_find(g, "e_end"))
        _drop_edge(g, "k")
        g["edges"].append({"key": "back", "from": "o_j", "to": "x_s"})  # loop, no terminal

    assert "no_end" in _codes(_mut(rewire), known_capabilities={"door.open"})


# -- small graph mutators -------------------------------------------------------


def _find(g: dict[str, Any], key: str) -> dict[str, Any]:
    return next(n for n in g["nodes"] if n["key"] == key)


def _edge(g: dict[str, Any], key: str) -> dict[str, Any]:
    return next(e for e in g["edges"] if e["key"] == key)


def _drop_edge(g: dict[str, Any], key: str) -> None:
    g["edges"] = [e for e in g["edges"] if e["key"] != key]


def _clear_condition(g: dict[str, Any], key: str) -> None:
    _edge(g, key).pop("condition", None)


def _clear_branch(g: dict[str, Any], key: str) -> None:
    _edge(g, key).pop("branch", None)


def _drop_prop(g: dict[str, Any], node: str, prop: str) -> None:
    _find(g, node).get("props", {}).pop(prop, None)


def _set_capability(g: dict[str, Any], value: str) -> None:
    _find(g, "f_act")["props"]["capability"] = value


def _make_cycle(g: dict[str, Any]) -> None:
    g["edges"].append({"key": "loop", "from": "f_doc", "to": "x_s"})
