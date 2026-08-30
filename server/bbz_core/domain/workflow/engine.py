"""Deterministic EPK token engine — AND / XOR / OR split & join.

Roadmap E05-08 / E05-09 (`.ai/WORKFLOW_EPK.md`, "Connector semantics"). Pure
domain code (ADR-0008): the engine takes a :class:`DerivedGraph`, the current
token multiset, an optional condition ``context`` and the operator
``decisions`` recorded so far, and returns the mutations to apply — no I/O,
and the same input always yields the same output. A crashed engine that
re-runs from the persisted token state therefore reaches the same result,
which is what makes step processing idempotent across a failover.

Node handling:

* **event** — pass-through: the token is consumed and a fresh token is put on
  every outgoing edge (a non-connector node has at most one, so this is a
  move). An event with no outgoing edge is an end.
* **function** — the token parks (``waiting``). Resuming it is
  :func:`resume_function`, driven by the step-completion command.
* **AND split** — consume, one active token per outgoing edge.
* **AND join** — parks; fires once a token is parked for *every* incoming edge.
* **XOR split** — exactly one branch: an operator decision if one was recorded,
  else the first branch (in edge-key order) whose rule-DSL ``condition`` holds,
  else the unconditioned default branch. If nothing resolves the token parks
  and waits for an operator decision — never a wrong path.
* **XOR join** — fires on the first token to arrive (only one ever will).
* **OR split** — one *or more* branches: an operator decision, else every
  branch whose ``condition`` holds or has none. If none resolve, the token
  parks.
* **OR join** — fires once a token has arrived and no other live token can
  still reach the join (so it waits for exactly the activated branch set).

Auto XOR / OR selections are reported in :attr:`EngineResult.decisions` so the
caller can persist them (and audit ``WORKFLOW_DECISION_MADE``).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from bbz_core.domain.workflow.graph import DerivedGraph, GraphEdge, GraphNode
from bbz_rule_dsl import Context, RuleDslError, evaluate, parse

_ACTIVE = "active"
_WAITING = "waiting"
_CONSUMED = "consumed"


class WorkflowEngineError(Exception):
    """The graph cannot be executed as given."""


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
class DecisionMade:
    """A branch selection the engine resolved automatically at a connector."""

    connector_node_key: str
    chosen_edge_keys: list[str]
    auto: bool = True


@dataclass(frozen=True)
class EngineResult:
    """Mutations the caller must persist, atomically, to advance the instance."""

    consumed: list[Any] = field(default_factory=list)  # ids of existing tokens
    parked: list[Any] = field(default_factory=list)  # ids of existing tokens -> waiting
    spawned: list[tuple[str, str | None]] = field(default_factory=list)  # (node_key, inbound edge)
    decisions: list[DecisionMade] = field(default_factory=list)
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
        self.reachable: dict[str, set[str]] = {n.key: self._descendants(n.key) for n in graph.nodes}

    def _descendants(self, start: str) -> set[str]:
        seen: set[str] = set()
        stack = [e.to_key for e in self.out.get(start, [])]
        while stack:
            key = stack.pop()
            if key in seen:
                continue
            seen.add(key)
            stack.extend(e.to_key for e in self.out.get(key, []))
        return seen


@dataclass
class _Run:
    idx: _Index
    graph: DerivedGraph
    context: Mapping[str, Any]
    decisions: Mapping[str, list[str]]
    made: list[DecisionMade] = field(default_factory=list)


def advance(
    graph: DerivedGraph,
    tokens: list[Token],
    *,
    context: Mapping[str, Any] | None = None,
    decisions: Mapping[str, list[str]] | None = None,
) -> EngineResult:
    """Process every active token until the instance is quiescent."""
    run = _mk_run(graph, context, decisions)
    work = [_mk_existing(t) for t in tokens]
    _run_loop(run, work)
    return _result(work, run)


def resume_function(
    graph: DerivedGraph,
    tokens: list[Token],
    node_key: str,
    *,
    context: Mapping[str, Any] | None = None,
    decisions: Mapping[str, list[str]] | None = None,
) -> EngineResult:
    """Consume the waiting token at ``node_key`` (a completed step), move it on,
    then advance. Raises :class:`StepNotWaitingError` if nothing is waiting there."""
    run = _mk_run(graph, context, decisions)
    work = [_mk_existing(t) for t in tokens]
    target = next((w for w in work if w.node_key == node_key and w.state == _WAITING), None)
    if target is None:
        raise StepNotWaitingError(f"no waiting token at node {node_key!r}")
    target.state = _CONSUMED
    _spawn_on(work, run.idx.out.get(node_key, []))
    _run_loop(run, work)
    return _result(work, run)


def _mk_run(
    graph: DerivedGraph,
    context: Mapping[str, Any] | None,
    decisions: Mapping[str, list[str]] | None,
) -> _Run:
    return _Run(
        idx=_Index(graph),
        graph=graph,
        context=context or {},
        decisions=decisions or {},
    )


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


def _run_loop(run: _Run, work: list[_W]) -> None:
    # Totality guard: every step either consumes a token or parks one, so a
    # graph that keeps producing active tokens forever (a cycle with no
    # function/join to absorb them) is bounded here rather than hanging.
    g = run.graph
    budget = (len(g.nodes) + len(g.edges) + len(work)) * (len(g.nodes) + 1) + 100
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
        _process(run, work, nxt)


def _process(run: _Run, work: list[_W], w: _W) -> None:
    node = run.idx.nodes.get(w.node_key)
    if node is None:
        raise WorkflowEngineError(f"token at unknown node {w.node_key!r}")

    if node.type == "event":
        w.state = _CONSUMED
        _spawn_on(work, run.idx.out.get(node.key, []))
        return

    if node.type == "function":
        w.state = _WAITING
        return

    if node.type == "connector":
        _connector(run, work, w, node)
        return

    raise WorkflowEngineError(f"unknown node type {node.type!r} at {w.node_key!r}")


def _connector(run: _Run, work: list[_W], w: _W, node: GraphNode) -> None:
    if node.connector_direction == "split":
        if node.connector_type == "and":
            w.state = _CONSUMED
            _spawn_on(work, run.idx.out.get(node.key, []))
            return
        _choice_split(run, work, w, node)
        return
    if node.connector_direction == "join":
        w.state = _WAITING
        if node.connector_type == "and":
            _maybe_fire_and_join(run, work, node.key)
        elif node.connector_type == "xor":
            _fire_choice_join(run, work, node.key)
        else:  # or
            _maybe_fire_or_join(run, work, node.key)
        return
    raise WorkflowEngineError(f"connector {node.key!r} has no split/join direction")


def _choice_split(run: _Run, work: list[_W], w: _W, node: GraphNode) -> None:
    exclusive = node.connector_type == "xor"
    out = run.idx.out.get(node.key, [])

    if node.key in run.decisions:
        wanted = set(run.decisions[node.key])
        chosen = [e for e in out if e.key in wanted]
        if not chosen:
            raise WorkflowEngineError(f"decision for {node.key!r} names no valid branch")
        if exclusive and len(chosen) != 1:
            raise WorkflowEngineError(
                f"an XOR decision for {node.key!r} must pick exactly one branch"
            )
        w.state = _CONSUMED
        _spawn_on(work, chosen)
        return

    auto = _auto_branches(run.context, out, exclusive=exclusive)
    if auto is None:
        # nothing resolves — wait for an operator decision, never a wrong path
        w.state = _WAITING
        return
    w.state = _CONSUMED
    _spawn_on(work, auto)
    run.made.append(DecisionMade(node.key, [e.key for e in auto], auto=True))


def _auto_branches(
    context: Mapping[str, Any], out: list[GraphEdge], *, exclusive: bool
) -> list[GraphEdge] | None:
    if exclusive:
        for edge in out:  # edge-key order -> deterministic
            if edge.condition is not None and _guard_true(edge.condition, context):
                return [edge]
        default = [e for e in out if e.condition is None]
        return [default[0]] if default else None
    picked = [e for e in out if e.condition is None or _guard_true(e.condition, context)]
    return picked or None


def _guard_true(condition: Mapping[str, Any], context: Mapping[str, Any]) -> bool:
    try:
        return bool(evaluate(parse(dict(condition)), Context(dict(context))))
    except RuleDslError:
        # a guard that cannot be evaluated is treated as "not satisfied"; a
        # structurally broken condition is caught by publish validation (E05-06).
        return False


def _spawn_on(work: list[_W], edges: list[GraphEdge]) -> None:
    for edge in edges:
        work.append(_W("spawned", None, edge.to_key, _ACTIVE, edge.key, was_active=False))


def _maybe_fire_and_join(run: _Run, work: list[_W], join_key: str) -> None:
    present = [w for w in work if w.node_key == join_key and w.state != _CONSUMED]
    arrived = {w.inbound for w in present}
    needed = {e.key for e in run.idx.inc.get(join_key, [])}
    if not needed or not needed <= arrived:
        return
    _fire_join(run, work, join_key, present)


def _fire_choice_join(run: _Run, work: list[_W], join_key: str) -> None:
    # XOR: exactly one branch ever carries a token, so the first arrival fires.
    present = [w for w in work if w.node_key == join_key and w.state != _CONSUMED]
    if present:
        _fire_join(run, work, join_key, present)


def _maybe_fire_or_join(run: _Run, work: list[_W], join_key: str) -> None:
    present = [w for w in work if w.node_key == join_key and w.state != _CONSUMED]
    if not present:  # pragma: no cover - a token was just parked here
        return
    still_coming = any(
        join_key in run.idx.reachable.get(w.node_key, set())
        for w in work
        if w.state in (_ACTIVE, _WAITING) and w.node_key != join_key
    )
    if still_coming:
        return
    _fire_join(run, work, join_key, present)


def _fire_join(run: _Run, work: list[_W], join_key: str, present: list[_W]) -> None:
    for w in present:
        w.state = _CONSUMED
    _spawn_on(work, run.idx.out.get(join_key, []))


def _result(work: list[_W], run: _Run) -> EngineResult:
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
        elif w.state == _ACTIVE:  # pragma: no cover - _run_loop leaves nothing active
            raise WorkflowEngineError("internal: spawned token still active after run")
    completed = not any(w.state in (_ACTIVE, _WAITING) for w in work)
    return EngineResult(
        consumed=consumed,
        parked=parked,
        spawned=spawned,
        decisions=list(run.made),
        completed=completed,
    )
