"""In-memory dry-run of an EPK workflow graph (roadmap E05-13).

Pure domain code (ADR-0008): no DB, no real ``external_action_outbox`` rows,
no real side effects — an admin can test a template before publishing it
(MASTER_PROMPT §33.3). The driver reuses the real engine
(:func:`bbz_core.domain.workflow.engine.advance` / ``resume_function``), so the
simulated path is the path the live runtime would take.

Operator steps are auto-completed (the admin supplies ``decisions`` for
branch points that do not resolve from ``context``); timer waits are
fast-forwarded; auto actions (integration / notification / event_update) are
recorded as **would-be** outbox rows, never enqueued.
"""

from __future__ import annotations

import uuid
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from bbz_core.domain.workflow.engine import (
    EngineResult,
    Token,
    advance,
    resume_function,
)
from bbz_core.domain.workflow.graph import DerivedGraph, GraphNode, derive_index
from bbz_core.domain.workflow.tasks import (
    AUTO_KINDS,
    TIMER_KINDS,
    outbox_action,
    step_dedupe_key,
    timer_seconds,
)

_SIM_INSTANCE = uuid.UUID(int=0)


@dataclass
class SimulationReport:
    status: str  # "completed" | "running" (blocked on a decision or operator step)
    visited_nodes: list[str] = field(default_factory=list)
    steps: list[dict[str, Any]] = field(default_factory=list)
    decisions: list[dict[str, Any]] = field(default_factory=list)
    outbox_dry_run: list[dict[str, Any]] = field(default_factory=list)
    pending_decisions: list[str] = field(default_factory=list)
    active_nodes: list[str] = field(default_factory=list)


@dataclass
class _Sim:
    graph: DerivedGraph
    context: Mapping[str, Any]
    decisions: dict[str, list[str]]
    report: SimulationReport
    tokens: list[Token] = field(default_factory=list)
    _next_id: int = 0

    def new_token(self, node_key: str, inbound: str | None, state: str = "waiting") -> Token:
        self._next_id += 1
        return Token(id=self._next_id, node_key=node_key, state=state, inbound_edge_key=inbound)


def simulate(
    definition: dict[str, Any],
    *,
    context: Mapping[str, Any] | None = None,
    decisions: Mapping[str, list[str]] | None = None,
) -> SimulationReport:
    graph = derive_index(definition)
    sim = _Sim(
        graph=graph,
        context=context or {},
        decisions=dict(decisions or {}),
        report=SimulationReport(status="running"),
    )
    sim.tokens = [sim.new_token(graph.start, None, state="active")]
    sim.report.visited_nodes.append(graph.start)
    _apply(sim, advance(graph, sim.tokens, context=sim.context, decisions=sim.decisions))

    budget = (len(graph.nodes) + len(graph.edges)) * 4 + 50
    for _ in range(budget):
        if not _act(sim):
            break
    else:  # pragma: no cover - budget only trips on a pathological graph
        raise ValueError("simulation did not settle")

    waiting = [t.node_key for t in sim.tokens]
    sim.report.active_nodes = sorted(set(waiting))
    sim.report.visited_nodes = _dedupe(sim.report.visited_nodes)
    sim.report.status = "completed" if not sim.tokens else "running"
    return sim.report


def _node(graph: DerivedGraph, key: str) -> GraphNode | None:
    return next((n for n in graph.nodes if n.key == key), None)


def _apply(sim: _Sim, res: EngineResult) -> None:
    consumed = set(res.consumed)
    sim.tokens = [t for t in sim.tokens if t.id not in consumed]
    for node_key, inbound in res.spawned:
        sim.tokens.append(sim.new_token(node_key, inbound))
        sim.report.visited_nodes.append(node_key)
    for d in res.decisions:
        sim.report.decisions.append(
            {
                "connector_node_key": d.connector_node_key,
                "chosen_branches": list(d.chosen_edge_keys),
                "auto": d.auto,
            }
        )


def _act(sim: _Sim) -> bool:
    """Advance one parked token; return False when nothing is actionable."""
    for tok in list(sim.tokens):
        node = _node(sim.graph, tok.node_key)
        if node is None:  # pragma: no cover - derive_index guarantees the node
            continue

        if node.type == "function":
            _run_function(sim, tok, node)
            return True

        if (
            node.type == "connector"
            and node.connector_direction == "split"
            and node.connector_type in ("xor", "or")
            and node.key not in sim.report.pending_decisions
        ):
            # a parked split has, by definition, no matching condition or
            # decision — record it as needing an operator choice and stop.
            sim.report.pending_decisions.append(node.key)
    return False


def _run_function(sim: _Sim, tok: Token, node: GraphNode) -> None:
    kind = node.function_kind or "manual"
    outcome = "completed"
    if kind in AUTO_KINDS:
        outcome = "dispatched (dry-run)"
        sim.report.outbox_dry_run.append(
            {
                "node_key": node.key,
                "action_type": outbox_action(kind),
                "dedupe_key": step_dedupe_key(_SIM_INSTANCE, node.key),
                "payload": {"kind": kind, "props": node.props},
            }
        )
    elif kind in TIMER_KINDS:
        outcome = f"waited {timer_seconds(node.props)}s (fast-forward)"

    sim.report.steps.append({"node_key": node.key, "kind": kind, "outcome": outcome})
    _apply(
        sim,
        resume_function(
            sim.graph,
            sim.tokens,
            node.key,
            context=sim.context,
            decisions=sim.decisions,
        ),
    )


def _dedupe(seq: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in seq:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def diff_definitions(before: dict[str, Any] | None, after: dict[str, Any]) -> dict[str, Any]:
    """A structural diff between two graph definitions — the basis of a changelog."""
    b_nodes = {n["key"]: n for n in (before or {}).get("nodes", [])}
    a_nodes = {n["key"]: n for n in after.get("nodes", [])}
    b_edges = {e["key"]: e for e in (before or {}).get("edges", [])}
    a_edges = {e["key"]: e for e in after.get("edges", [])}
    n_changed = [k for k in a_nodes.keys() & b_nodes.keys() if a_nodes[k] != b_nodes[k]]
    e_changed = [k for k in a_edges.keys() & b_edges.keys() if a_edges[k] != b_edges[k]]
    return {
        "nodes_added": sorted(a_nodes.keys() - b_nodes.keys()),
        "nodes_removed": sorted(b_nodes.keys() - a_nodes.keys()),
        "nodes_changed": sorted(n_changed),
        "edges_added": sorted(a_edges.keys() - b_edges.keys()),
        "edges_removed": sorted(b_edges.keys() - a_edges.keys()),
        "edges_changed": sorted(e_changed),
        "start_changed": (before or {}).get("start") != after.get("start"),
    }
