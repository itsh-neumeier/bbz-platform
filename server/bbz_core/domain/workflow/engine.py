"""Deterministic EPK token engine — AND-split / AND-join + token semantics.

Roadmap E05-08 (`.ai/WORKFLOW_EPK.md`, "Connector semantics"). Pure domain
code (ADR-0008): the engine takes a :class:`DerivedGraph` plus the current
token multiset and returns the mutations to apply — no I/O, and the same
input always yields the same output. A crashed engine that re-runs from the
persisted token state therefore reaches the same result, which is what makes
step processing idempotent across a failover.

Scope of this module:

* **event** node — pass-through: the token is consumed and a fresh token is
  put on every outgoing edge (a non-connector node has at most one, so this is
  a move). An event with no outgoing edge is an end.
* **function** node — the token parks (``waiting``). Actually executing the
  task (and thus resuming the token) is :func:`resume_function`, driven by the
  step-completion command (E05-10 owns the task runners themselves).
* **AND split** — consume, one active token per outgoing edge.
* **AND join** — the token parks; once a token is parked for *every* incoming
  edge, all of them are consumed and one token continues on the single
  outgoing edge.

XOR / OR split and join raise :class:`WorkflowEngineError` here — they are
E05-09 (#76).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from bbz_core.domain.workflow.graph import DerivedGraph, GraphEdge, GraphNode

_ACTIVE = "active"
_WAITING = "waiting"
_CONSUMED = "consumed"


class WorkflowEngineError(Exception):
    """The graph cannot be executed by this engine (yet)."""


class StepNotWaitingError(WorkflowEngineError):
    """resume_function() was asked to resume a node with no waiting token."""


@dataclass(frozen=True)
class Token:
    """A live token as loaded from ``workflow_tokens`` (state != consumed)."""

    id: Any
    node_key: str
    state: str  # "active" | "waiting"
    inbound_edge_key: str | None = None


@dataclass(frozen=True)
class EngineResult:
    """Mutations the caller must persist, atomically, to advance the instance."""

    consumed: list[Any] = field(default_factory=list)  # ids of existing tokens
    parked: list[Any] = field(default_factory=list)  # ids of existing tokens -> waiting
    spawned: list[tuple[str, str | None]] = field(default_factory=list)  # (node_key, inbound edge)
    completed: bool = False


@dataclass
class _W:
    origin: str  # "existing" | "spawned"
    id: Any
    node_key: str
    state: str  # active | waiting | consumed
    inbound: str | None
    was_active: bool  # input state was "active" (existing tokens only)


class _Index:
    def __init__(self, graph: DerivedGraph) -> None:
        self.nodes: dict[str, GraphNode] = {n.key: n for n in graph.nodes}
        self.out: dict[str, list[GraphEdge]] = {n.key: [] for n in graph.nodes}
        self.inc: dict[str, list[GraphEdge]] = {n.key: [] for n in graph.nodes}
        for e in sorted(graph.edges, key=lambda e: e.key):
            self.out[e.from_key].append(e)
            self.inc[e.to_key].append(e)


def advance(graph: DerivedGraph, tokens: list[Token]) -> EngineResult:
    """Process every active token until the instance is quiescent."""
    idx = _Index(graph)
    work = [_mk_existing(t) for t in tokens]
    _run(idx, work, graph)
    return _result(work)


def resume_function(graph: DerivedGraph, tokens: list[Token], node_key: str) -> EngineResult:
    """Consume the waiting token at ``node_key`` (a completed step), move it on,
    then advance. Raises :class:`StepNotWaitingError` if nothing is waiting there."""
    idx = _Index(graph)
    work = [_mk_existing(t) for t in tokens]
    target = next((w for w in work if w.node_key == node_key and w.state == _WAITING), None)
    if target is None:
        raise StepNotWaitingError(f"no waiting token at node {node_key!r}")
    target.state = _CONSUMED
    for edge in idx.out.get(node_key, []):
        work.append(_W("spawned", None, edge.to_key, _ACTIVE, edge.key, was_active=False))
    _run(idx, work, graph)
    return _result(work)


def _mk_existing(t: Token) -> _W:
    if t.state not in (_ACTIVE, _WAITING):
        raise WorkflowEngineError(f"token {t.id} has unexpected state {t.state!r}")
    return _W(
        origin="existing",
        id=t.id,
        node_key=t.node_key,
        state=t.state,
        inbound=t.inbound_edge_key,
        was_active=t.state == _ACTIVE,
    )


def _run(idx: _Index, work: list[_W], graph: DerivedGraph) -> None:
    # Totality guard: every step either consumes a token or parks one, so a
    # graph that keeps producing active tokens forever (a cycle with no
    # function/join to absorb them) is bounded here rather than hanging.
    budget = (len(graph.nodes) + len(graph.edges) + len(work)) * (len(graph.nodes) + 1) + 100
    steps = 0
    while True:
        nxt = next((w for w in work if w.state == _ACTIVE), None)
        if nxt is None:
            return
        steps += 1
        if steps > budget:
            raise WorkflowEngineError(
                "engine did not settle — a cycle without a bounded re-entry rule?"
            )
        _process(idx, work, nxt)


def _process(idx: _Index, work: list[_W], w: _W) -> None:
    node = idx.nodes.get(w.node_key)
    if node is None:
        raise WorkflowEngineError(f"token at unknown node {w.node_key!r}")

    if node.type == "event":
        w.state = _CONSUMED
        _spawn_successors(idx, work, w.node_key)
        return

    if node.type == "function":
        w.state = _WAITING
        return

    if node.type == "connector":
        if node.connector_direction == "split":
            if node.connector_type != "and":
                raise WorkflowEngineError(
                    f"{node.connector_type!r} split is not supported yet (E05-09)"
                )
            w.state = _CONSUMED
            _spawn_successors(idx, work, w.node_key)
            return
        if node.connector_direction == "join":
            if node.connector_type != "and":
                raise WorkflowEngineError(
                    f"{node.connector_type!r} join is not supported yet (E05-09)"
                )
            w.state = _WAITING
            _maybe_fire_and_join(idx, work, node.key)
            return
        raise WorkflowEngineError(f"connector {node.key!r} has no split/join direction")

    raise WorkflowEngineError(f"unknown node type {node.type!r} at {w.node_key!r}")


def _spawn_successors(idx: _Index, work: list[_W], node_key: str) -> None:
    for edge in idx.out.get(node_key, []):
        work.append(_W("spawned", None, edge.to_key, _ACTIVE, edge.key, was_active=False))


def _maybe_fire_and_join(idx: _Index, work: list[_W], join_key: str) -> None:
    present = [w for w in work if w.node_key == join_key and w.state != _CONSUMED]
    arrived = {w.inbound for w in present}
    needed = {e.key for e in idx.inc.get(join_key, [])}
    if not needed or not needed <= arrived:
        return
    for w in present:
        w.state = _CONSUMED
    for edge in idx.out.get(join_key, []):
        work.append(_W("spawned", None, edge.to_key, _ACTIVE, edge.key, was_active=False))


def _result(work: list[_W]) -> EngineResult:
    consumed: list[Any] = []
    parked: list[Any] = []
    spawned: list[tuple[str, str | None]] = []
    for w in work:
        if w.origin == "existing":
            if w.state == _CONSUMED:
                consumed.append(w.id)
            elif w.state == _WAITING and w.was_active:
                parked.append(w.id)
        elif w.state == _WAITING:
            spawned.append((w.node_key, w.inbound))
        elif w.state == _ACTIVE:  # pragma: no cover - _run leaves nothing active
            raise WorkflowEngineError("internal: spawned token still active after run")
    completed = not any(w.state in (_ACTIVE, _WAITING) for w in work)
    return EngineResult(consumed=consumed, parked=parked, spawned=spawned, completed=completed)
