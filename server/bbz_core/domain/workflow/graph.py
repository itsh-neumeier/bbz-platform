"""EPK workflow graph: schema validation + deterministic index derivation.

Pure domain code (ADR-0008): no I/O. :func:`validate_graph` checks a
``definition`` against ``workflow.graph.v1`` plus a few structural rules that
JSON Schema cannot express (unique keys, edge endpoints exist, ``start`` points
at a real node). :func:`derive_index` flattens the graph into ordered
node/edge rows — the same input always yields the same output, so the derived
index tables (E05-04) rebuild consistently. Full publish validation
(reachability, split/join cardinality, …) is E05-06.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

import jsonschema

from bbz_event_schemas import load_schema

_SCHEMA = "workflow.graph.v1"


class WorkflowGraphError(ValueError):
    pass


@lru_cache
def _validator() -> jsonschema.Draft202012Validator:
    return jsonschema.Draft202012Validator(load_schema(_SCHEMA))


@dataclass(frozen=True)
class GraphNode:
    key: str
    type: str
    label: str | None = None
    function_kind: str | None = None
    connector_type: str | None = None
    connector_direction: str | None = None
    props: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GraphEdge:
    key: str
    from_key: str
    to_key: str
    branch: str | None = None
    condition: dict[str, Any] | None = None


@dataclass(frozen=True)
class DerivedGraph:
    start: str
    nodes: list[GraphNode]
    edges: list[GraphEdge]


def validate_graph(definition: dict[str, Any]) -> None:
    errors = sorted(_validator().iter_errors(definition), key=str)
    if errors:
        raise WorkflowGraphError("; ".join(e.message for e in errors))

    nodes = definition["nodes"]
    keys = [n["key"] for n in nodes]
    dupes = sorted({k for k in keys if keys.count(k) > 1})
    if dupes:
        raise WorkflowGraphError(f"duplicate node keys: {dupes}")
    keyset = set(keys)

    if definition["start"] not in keyset:
        raise WorkflowGraphError(f"start node {definition['start']!r} does not exist")

    edge_keys = [e["key"] for e in definition["edges"]]
    edge_dupes = sorted({k for k in edge_keys if edge_keys.count(k) > 1})
    if edge_dupes:
        raise WorkflowGraphError(f"duplicate edge keys: {edge_dupes}")
    for edge in definition["edges"]:
        for side in ("from", "to"):
            if edge[side] not in keyset:
                raise WorkflowGraphError(
                    f"edge {edge['key']!r} {side} node {edge[side]!r} does not exist"
                )


def derive_index(definition: dict[str, Any]) -> DerivedGraph:
    """Validate then flatten to ordered rows (deterministic by key)."""
    validate_graph(definition)
    nodes = [
        GraphNode(
            key=n["key"],
            type=n["type"],
            label=n.get("label"),
            function_kind=n.get("kind"),
            connector_type=n.get("connector"),
            connector_direction=n.get("direction"),
            props=dict(n.get("props", {})),
        )
        for n in sorted(definition["nodes"], key=lambda n: n["key"])
    ]
    edges = [
        GraphEdge(
            key=e["key"],
            from_key=e["from"],
            to_key=e["to"],
            branch=e.get("branch"),
            condition=e.get("condition"),
        )
        for e in sorted(definition["edges"], key=lambda e: e["key"])
    ]
    return DerivedGraph(start=definition["start"], nodes=nodes, edges=edges)
