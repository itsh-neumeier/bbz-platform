"""Deterministic EPK token engine: AND / XOR / OR split & join (E05-08/09)."""

from __future__ import annotations

from typing import Any

import pytest

from bbz_core.domain.workflow import derive_index
from bbz_core.domain.workflow.engine import (
    DerivedGraph,
    GraphEdge,
    GraphNode,
    StepNotWaitingError,
    Token,
    WorkflowEngineError,
    advance,
    resume_function,
)


def _cond(field: str, value: Any) -> dict[str, Any]:
    return {"op": "eq", "args": [{"field": field}, value]}


# e0 --a--> as =and split=> f1, f2 (functions) --> aj =and join=> e1 (end)
_DIAMOND = {
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


def test_and_split_parks_a_token_on_every_branch() -> None:
    graph = derive_index(_DIAMOND)
    res = advance(graph, [Token(id=1, node_key="e0", state="active")])

    assert res.consumed == [1]
    assert not res.completed
    assert sorted(res.spawned) == [("f1", "b"), ("f2", "c")]


def test_and_join_waits_for_all_incoming_branches() -> None:
    graph = derive_index(_DIAMOND)
    parked = [
        Token(id=10, node_key="f1", state="waiting", inbound_edge_key="b"),
        Token(id=11, node_key="f2", state="waiting", inbound_edge_key="c"),
    ]

    # first branch completes -> a token now waits at the join, nothing fires
    res1 = resume_function(graph, parked, "f1")
    assert res1.consumed == [10]
    assert res1.spawned == [("aj", "d")]
    assert not res1.completed

    # second branch completes -> join fires, run reaches the end, instance done
    after1 = [
        Token(id=11, node_key="f2", state="waiting", inbound_edge_key="c"),
        Token(id=20, node_key="aj", state="waiting", inbound_edge_key="d"),
    ]
    res2 = resume_function(graph, after1, "f2")
    assert set(res2.consumed) == {11, 20}
    assert res2.spawned == []
    assert res2.completed


def test_a_lone_end_event_completes_immediately() -> None:
    graph = derive_index({"start": "e0", "nodes": [{"key": "e0", "type": "event"}], "edges": []})
    res = advance(graph, [Token(id=1, node_key="e0", state="active")])
    assert res.consumed == [1]
    assert res.completed


def test_a_function_node_just_parks() -> None:
    graph = derive_index(
        {
            "start": "e0",
            "nodes": [
                {"key": "e0", "type": "event"},
                {"key": "f", "type": "function", "kind": "manual"},
            ],
            "edges": [{"key": "a", "from": "e0", "to": "f"}],
        }
    )
    res = advance(graph, [Token(id=1, node_key="e0", state="active")])
    assert res.consumed == [1]
    assert res.spawned == [("f", "a")]
    assert not res.completed


def test_a_parked_function_token_is_left_untouched_by_advance() -> None:
    graph = derive_index(_DIAMOND)
    res = advance(graph, [Token(id=1, node_key="f1", state="waiting", inbound_edge_key="b")])
    assert res == type(res)()  # nothing consumed/parked/spawned, not completed


def test_an_existing_active_token_at_a_function_is_parked() -> None:
    graph = derive_index(_DIAMOND)
    res = advance(graph, [Token(id=7, node_key="f1", state="active", inbound_edge_key="b")])
    assert res.parked == [7]
    assert res.consumed == [] and res.spawned == []
    assert not res.completed


def test_resume_without_a_waiting_token_is_an_error() -> None:
    graph = derive_index(_DIAMOND)
    with pytest.raises(StepNotWaitingError):
        resume_function(graph, [Token(id=1, node_key="e0", state="active")], "f1")


# e0 -> xs (xor split): b -> f1 [priority==critical], c -> f2 (default)
#                       f1,f2 -> xj (xor join) -> e1
_XOR = {
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
        {"key": "b", "from": "xs", "to": "f1", "condition": _cond("event_priority", "critical")},
        {"key": "c", "from": "xs", "to": "f2"},
        {"key": "d", "from": "f1", "to": "xj"},
        {"key": "e", "from": "f2", "to": "xj"},
        {"key": "f", "from": "xj", "to": "e1"},
    ],
}

# e0 -> os (or split): both branches labelled + guarded; f1,f2 -> oj (or join) -> e1
_OR = {
    "start": "e0",
    "nodes": [
        {"key": "e0", "type": "event"},
        {"key": "os", "type": "connector", "connector": "or", "direction": "split"},
        {"key": "f1", "type": "function", "kind": "manual"},
        {"key": "f2", "type": "function", "kind": "manual"},
        {"key": "oj", "type": "connector", "connector": "or", "direction": "join"},
        {"key": "e1", "type": "event"},
    ],
    "edges": [
        {"key": "a", "from": "e0", "to": "os"},
        {
            "key": "b",
            "from": "os",
            "to": "f1",
            "branch": "left",
            "condition": _cond("source", "bma"),
        },
        {
            "key": "c",
            "from": "os",
            "to": "f2",
            "branch": "right",
            "condition": _cond("event_priority", "critical"),
        },
        {"key": "d", "from": "f1", "to": "oj"},
        {"key": "e", "from": "f2", "to": "oj"},
        {"key": "f", "from": "oj", "to": "e1"},
    ],
}


def test_xor_split_auto_picks_the_first_matching_branch() -> None:
    graph = derive_index(_XOR)
    res = advance(
        graph, [Token(id=1, node_key="e0", state="active")], context={"event_priority": "critical"}
    )
    assert res.spawned == [("f1", "b")]
    assert [(d.connector_node_key, d.chosen_edge_keys, d.auto) for d in res.decisions] == [
        ("xs", ["b"], True)
    ]


def test_xor_split_falls_back_to_the_unconditioned_default() -> None:
    graph = derive_index(_XOR)
    res = advance(
        graph, [Token(id=1, node_key="e0", state="active")], context={"event_priority": "low"}
    )
    assert res.spawned == [("f2", "c")]
    assert res.decisions[0].chosen_edge_keys == ["c"]


def test_xor_split_without_a_resolution_parks_for_an_operator() -> None:
    graph = derive_index(
        {
            "start": "e0",
            "nodes": [
                {"key": "e0", "type": "event"},
                {"key": "xs", "type": "connector", "connector": "xor", "direction": "split"},
                {"key": "f1", "type": "function", "kind": "manual"},
                {"key": "f2", "type": "function", "kind": "manual"},
            ],
            "edges": [
                {"key": "a", "from": "e0", "to": "xs"},
                {"key": "b", "from": "xs", "to": "f1", "condition": _cond("status", "x")},
                {"key": "c", "from": "xs", "to": "f2", "condition": _cond("status", "y")},
            ],
        }
    )
    res = advance(graph, [Token(id=1, node_key="e0", state="active")], context={"status": "other"})
    assert res.spawned == [("xs", "a")]  # a token now waits at the connector
    assert res.decisions == []
    assert not res.completed


def test_xor_split_honours_an_operator_decision() -> None:
    graph = derive_index(_XOR)
    res = advance(
        graph,
        [Token(id=1, node_key="xs", state="active", inbound_edge_key="a")],
        decisions={"xs": ["c"]},
    )
    assert res.consumed == [1]
    assert res.spawned == [("f2", "c")]
    assert res.decisions == []  # already persisted, not re-reported


def test_xor_join_fires_on_the_first_token() -> None:
    graph = derive_index(_XOR)
    res = resume_function(
        graph,
        [Token(id=9, node_key="f2", state="waiting", inbound_edge_key="c")],
        "f2",
    )
    assert res.consumed == [9]
    assert res.completed  # f2 -> xj -> e1, nothing else outstanding


def test_a_broken_guard_counts_as_not_satisfied() -> None:
    graph = derive_index(
        {
            "start": "e0",
            "nodes": [
                {"key": "e0", "type": "event"},
                {"key": "xs", "type": "connector", "connector": "xor", "direction": "split"},
                {"key": "f1", "type": "function", "kind": "manual"},
                {"key": "f2", "type": "function", "kind": "manual"},
            ],
            "edges": [
                {"key": "a", "from": "e0", "to": "xs"},
                {
                    "key": "b",
                    "from": "xs",
                    "to": "f1",
                    "condition": {"op": "lt", "args": [{"field": "event_priority"}, 5]},
                },
                {"key": "c", "from": "xs", "to": "f2"},
            ],
        }
    )
    res = advance(
        graph, [Token(id=1, node_key="e0", state="active")], context={"event_priority": "high"}
    )
    assert res.spawned == [("f2", "c")]  # the type-mismatched guard did not match


def test_a_decision_naming_no_valid_branch_is_rejected() -> None:
    graph = derive_index(_XOR)
    with pytest.raises(WorkflowEngineError, match="no valid branch"):
        advance(
            graph,
            [Token(id=1, node_key="xs", state="active", inbound_edge_key="a")],
            decisions={"xs": ["zzz"]},
        )


def test_an_xor_decision_with_two_branches_is_rejected() -> None:
    graph = derive_index(_XOR)
    with pytest.raises(WorkflowEngineError, match="exactly one branch"):
        advance(
            graph,
            [Token(id=1, node_key="xs", state="active", inbound_edge_key="a")],
            decisions={"xs": ["b", "c"]},
        )


def test_or_split_activates_every_matching_branch() -> None:
    graph = derive_index(_OR)
    res = advance(
        graph,
        [Token(id=1, node_key="e0", state="active")],
        context={"source": "bma", "event_priority": "critical"},
    )
    assert sorted(res.spawned) == [("f1", "b"), ("f2", "c")]
    assert res.decisions[0].chosen_edge_keys == ["b", "c"]


def test_or_split_can_activate_a_single_branch() -> None:
    graph = derive_index(_OR)
    res = advance(
        graph,
        [Token(id=1, node_key="e0", state="active")],
        context={"source": "bma", "event_priority": "low"},
    )
    assert res.spawned == [("f1", "b")]


def test_or_split_without_a_resolution_parks() -> None:
    graph = derive_index(_OR)
    res = advance(
        graph,
        [Token(id=1, node_key="e0", state="active")],
        context={"source": "manual", "event_priority": "low"},
    )
    assert res.spawned == [("os", "a")]
    assert res.decisions == []


def test_or_join_waits_for_the_whole_activated_branch_set() -> None:
    graph = derive_index(_OR)
    ctx = {"source": "bma", "event_priority": "critical"}
    both_waiting = [
        Token(id=1, node_key="f1", state="waiting", inbound_edge_key="b"),
        Token(id=2, node_key="f2", state="waiting", inbound_edge_key="c"),
    ]
    # only one branch done -> the OR join must keep waiting for the other
    res1 = resume_function(graph, both_waiting, "f1", context=ctx)
    assert res1.consumed == [1]
    assert not res1.completed
    assert ("oj", "d") in res1.spawned

    after1 = [
        Token(id=2, node_key="f2", state="waiting", inbound_edge_key="c"),
        Token(id=3, node_key="oj", state="waiting", inbound_edge_key="d"),
    ]
    res2 = resume_function(graph, after1, "f2", context=ctx)
    assert set(res2.consumed) == {2, 3}
    assert res2.completed


def test_a_connector_without_a_direction_is_rejected() -> None:
    graph = DerivedGraph(
        start="c",
        nodes=[GraphNode(key="c", type="connector", connector_type="and")],
        edges=[],
    )
    with pytest.raises(WorkflowEngineError, match="split/join direction"):
        advance(graph, [Token(id=1, node_key="c", state="active")])


def test_an_unknown_node_type_is_rejected() -> None:
    graph = DerivedGraph(start="x", nodes=[GraphNode(key="x", type="gateway")], edges=[])
    with pytest.raises(WorkflowEngineError, match="unknown node type"):
        advance(graph, [Token(id=1, node_key="x", state="active")])


def test_a_token_at_a_missing_node_is_rejected() -> None:
    graph = DerivedGraph(start="a", nodes=[GraphNode(key="a", type="event")], edges=[])
    with pytest.raises(WorkflowEngineError, match="unknown node"):
        advance(graph, [Token(id=1, node_key="ghost", state="active")])


def test_a_token_in_a_bad_state_is_rejected() -> None:
    graph = derive_index(_DIAMOND)
    with pytest.raises(WorkflowEngineError, match="unexpected state"):
        advance(graph, [Token(id=1, node_key="e0", state="consumed")])


def test_a_cycle_without_a_parking_node_is_bounded_not_hung() -> None:
    graph = DerivedGraph(
        start="e0",
        nodes=[GraphNode(key="e0", type="event"), GraphNode(key="e1", type="event")],
        edges=[
            GraphEdge(key="a", from_key="e0", to_key="e1"),
            GraphEdge(key="b", from_key="e1", to_key="e0"),
        ],
    )
    with pytest.raises(WorkflowEngineError, match="did not settle"):
        advance(graph, [Token(id=1, node_key="e0", state="active")])
