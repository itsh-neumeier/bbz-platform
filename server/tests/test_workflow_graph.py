"""EPK graph: schema validation, deterministic index derivation, rebuild (E05-04)."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.domain.workflow import WorkflowGraphError, derive_index, validate_graph
from bbz_core.infra.models.workflow import (
    WorkflowGraphEdge,
    WorkflowGraphNode,
    WorkflowTemplate,
    WorkflowTemplateVersion,
)
from bbz_core.infra.repositories.workflow_graph import rebuild_graph_index

_GRAPH: dict[str, Any] = {
    "start": "e_call",
    "nodes": [
        {"key": "e_call", "type": "event", "label": "BMA-Anruf eingegangen"},
        {"key": "x1", "type": "connector", "connector": "xor", "direction": "split"},
        {
            "key": "f_confirm",
            "type": "function",
            "kind": "confirmation",
            "label": "Lage bestätigen",
        },
        {"key": "f_doc", "type": "function", "kind": "documentation"},
        {"key": "j1", "type": "connector", "connector": "xor", "direction": "join"},
        {"key": "e_done", "type": "event", "label": "Abgeschlossen"},
    ],
    "edges": [
        {"key": "a", "from": "e_call", "to": "x1"},
        {
            "key": "b",
            "from": "x1",
            "to": "f_confirm",
            "branch": "real",
            "condition": {"op": "eq", "args": [{"field": "event_priority"}, "critical"]},
        },
        {"key": "c", "from": "x1", "to": "f_doc", "branch": "false_alarm"},
        {"key": "d", "from": "f_confirm", "to": "j1"},
        {"key": "e", "from": "f_doc", "to": "j1"},
        {"key": "f", "from": "j1", "to": "e_done"},
    ],
}


def test_valid_epk_graph_passes() -> None:
    validate_graph(_GRAPH)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda g: g["nodes"].append({"key": "bad", "type": "function"}),  # kind missing
        lambda g: g["nodes"].append({"key": "c9", "type": "connector", "connector": "and"}),
        lambda g: g["edges"].append({"key": "z", "from": "e_call", "to": "ghost"}),
        lambda g: g.update(start="ghost"),
        lambda g: g["nodes"].append({"key": "e_call", "type": "event"}),  # dup key
        lambda g: g["edges"].append({"key": "a", "from": "e_call", "to": "x1"}),  # dup edge key
    ],
)
def test_invalid_graphs_are_rejected(mutate: Any) -> None:
    import copy

    g = copy.deepcopy(_GRAPH)
    mutate(g)
    with pytest.raises(WorkflowGraphError):
        validate_graph(g)


def test_derive_index_is_deterministic_and_ordered() -> None:
    import copy

    a = derive_index(_GRAPH)
    shuffled = copy.deepcopy(_GRAPH)
    shuffled["nodes"].reverse()
    shuffled["edges"].reverse()
    b = derive_index(shuffled)
    assert [n.key for n in a.nodes] == [n.key for n in b.nodes] == sorted(n.key for n in a.nodes)
    assert [e.key for e in a.edges] == [e.key for e in b.edges]
    xor = next(n for n in a.nodes if n.key == "x1")
    assert (xor.connector_type, xor.connector_direction) == ("xor", "split")
    b_edge = next(e for e in a.edges if e.key == "b")
    assert b_edge.branch == "real" and b_edge.condition is not None


async def test_rebuild_graph_index_populates_and_is_idempotent(db: object) -> None:
    s = db  # type: ignore[assignment]
    assert isinstance(s, AsyncSession)
    async with s.begin():
        tpl = WorkflowTemplate(key=f"k-{uuid.uuid4().hex[:8]}", name="BMA")
        s.add(tpl)
        await s.flush()
        v = WorkflowTemplateVersion(
            template_id=tpl.id, version_no=1, lifecycle="draft", definition=_GRAPH
        )
        s.add(v)
        await s.flush()
        vid = v.id
        n1, e1 = await rebuild_graph_index(s, template_version_id=vid, definition=_GRAPH)

    assert (n1, e1) == (6, 6)

    async with s.begin():
        n2, e2 = await rebuild_graph_index(s, template_version_id=vid, definition=_GRAPH)
    assert (n2, e2) == (6, 6)

    nodes = (
        (
            await s.execute(
                select(WorkflowGraphNode.node_key)
                .where(WorkflowGraphNode.template_version_id == vid)
                .order_by(WorkflowGraphNode.node_key)
            )
        )
        .scalars()
        .all()
    )
    assert list(nodes) == sorted(n["key"] for n in _GRAPH["nodes"])
    edge_count = len(
        (
            await s.execute(
                select(WorkflowGraphEdge.id).where(WorkflowGraphEdge.template_version_id == vid)
            )
        )
        .scalars()
        .all()
    )
    assert edge_count == 6  # not doubled by the second rebuild
