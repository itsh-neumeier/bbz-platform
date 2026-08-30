"""Deterministic EPK token engine: AND split/join, parking, guards (E05-08)."""

from __future__ import annotations

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


@pytest.mark.parametrize("direction", ["split", "join"])
def test_xor_and_or_are_not_supported_yet(direction: str) -> None:
    nodes = [
        GraphNode(key="e0", type="event"),
        GraphNode(key="c", type="connector", connector_type="xor", connector_direction=direction),
    ]
    graph = DerivedGraph(
        start="e0", nodes=nodes, edges=[GraphEdge(key="a", from_key="e0", to_key="c")]
    )
    with pytest.raises(WorkflowEngineError, match="E05-09"):
        advance(graph, [Token(id=1, node_key="e0", state="active")])


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
