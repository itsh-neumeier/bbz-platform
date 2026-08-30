"""Publish-time validation of an EPK workflow graph (roadmap E05-06).

Pure domain code. Beyond the structural checks in :func:`validate_graph`, a
graph may only be published if it is *semantically* sound (`.ai/WORKFLOW_EPK.md`
"Publish validation" checklist). :func:`validate_publishable` returns a list of
:class:`ValidationIssue` — an empty list means "publishable".
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from bbz_core.domain.workflow.graph import DerivedGraph, WorkflowGraphError, derive_index

#: function kinds and the ``props`` key each one requires
_REQUIRED_PROPS: dict[str, str] = {
    "integration_action": "capability",
    "notification": "channel",
    "timer": "duration_seconds",
}


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    message: str
    node_key: str | None = None


def _by_key(graph: DerivedGraph) -> dict[str, Any]:
    return {n.key: n for n in graph.nodes}


def _out(graph: DerivedGraph) -> dict[str, list[Any]]:
    m: dict[str, list[Any]] = {n.key: [] for n in graph.nodes}
    for e in graph.edges:
        m[e.from_key].append(e)
    return m


def _in(graph: DerivedGraph) -> dict[str, list[Any]]:
    m: dict[str, list[Any]] = {n.key: [] for n in graph.nodes}
    for e in graph.edges:
        m[e.to_key].append(e)
    return m


def _reachable(start: str, out: dict[str, list[Any]]) -> set[str]:
    seen: set[str] = set()
    stack = [start]
    while stack:
        key = stack.pop()
        if key in seen:
            continue
        seen.add(key)
        stack.extend(e.to_key for e in out.get(key, []))
    return seen


def _has_cycle(start: str, out: dict[str, list[Any]]) -> bool:
    colour: dict[str, int] = {}  # 0 = visiting, 1 = done

    def visit(key: str) -> bool:
        colour[key] = 0
        for edge in out.get(key, []):
            nxt = edge.to_key
            if colour.get(nxt) == 0:
                return True
            if nxt not in colour and visit(nxt):
                return True
        colour[key] = 1
        return False

    return visit(start)


def validate_publishable(
    definition: dict[str, Any],
    *,
    known_capabilities: Iterable[str] | None = None,
) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    try:
        graph = derive_index(definition)
    except WorkflowGraphError as exc:
        return [ValidationIssue("structure", str(exc))]

    nodes = _by_key(graph)
    out, inc = _out(graph), _in(graph)
    caps = frozenset(known_capabilities) if known_capabilities is not None else None

    # 1. start behaviour: an event node, with no incoming edge
    start = nodes[graph.start]
    if start.type != "event":
        issues.append(
            ValidationIssue("start_not_event", "the start node must be an event", start.key)
        )
    if inc[start.key]:
        issues.append(
            ValidationIssue(
                "start_has_predecessor", "the start node must have no incoming edge", start.key
            )
        )

    # 2/3. reachability + orphans + at least one reachable end
    reach = _reachable(graph.start, out)
    for n in graph.nodes:
        if n.key not in reach:
            issues.append(ValidationIssue("orphan", "node is unreachable from start", n.key))
    ends = [n.key for n in graph.nodes if not out[n.key]]
    if not any(e in reach for e in ends):
        issues.append(ValidationIssue("no_end", "no end node is reachable from start"))

    # 4. cardinality
    for n in graph.nodes:
        o, i = len(out[n.key]), len(inc[n.key])
        if n.type == "connector":
            if n.connector_direction == "split" and not (i == 1 and o >= 2):
                issues.append(
                    ValidationIssue(
                        "split_cardinality", f"a split needs 1 in / >=2 out (has {i}/{o})", n.key
                    )
                )
            if n.connector_direction == "join" and not (i >= 2 and o == 1):
                issues.append(
                    ValidationIssue(
                        "join_cardinality", f"a join needs >=2 in / 1 out (has {i}/{o})", n.key
                    )
                )
        elif o > 1:
            issues.append(
                ValidationIssue("branch_without_connector", "only connectors may branch", n.key)
            )

    # 5/6. XOR resolvable, OR trackable
    for n in graph.nodes:
        if n.type != "connector" or n.connector_direction != "split":
            continue
        branches = out[n.key]
        if n.connector_type == "xor":
            no_condition = [e for e in branches if e.condition is None]
            if len(no_condition) > 1:
                issues.append(
                    ValidationIssue(
                        "xor_unresolvable",
                        "an XOR split needs a condition on every branch but at most one default",
                        n.key,
                    )
                )
        if n.connector_type == "or" and any(e.branch is None for e in branches):
            issues.append(
                ValidationIssue(
                    "or_untrackable", "every OR-split branch needs a branch label", n.key
                )
            )

    # 7. required props per function kind
    for n in graph.nodes:
        if n.type != "function":
            continue
        need = _REQUIRED_PROPS.get(n.function_kind or "")
        if need and need not in n.props:
            issues.append(
                ValidationIssue("missing_prop", f"{n.function_kind} needs props.{need}", n.key)
            )
        # 8. integration action references a real capability
        if n.function_kind == "integration_action" and caps is not None:
            cap = n.props.get("capability")
            if cap not in caps:
                issues.append(
                    ValidationIssue(
                        "unknown_capability", f"unknown integration capability {cap!r}", n.key
                    )
                )

    # 9. no unbounded loop (a cycle with no explicit re-entry bound)
    if _has_cycle(graph.start, out):
        bounded = any(n.type == "connector" and "reentry" in n.props for n in graph.nodes)
        if not bounded:
            issues.append(
                ValidationIssue("unbounded_loop", "graph has a cycle with no bounded re-entry rule")
            )

    return issues
