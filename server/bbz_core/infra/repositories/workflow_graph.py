"""Rebuild the derived workflow-graph index for a template version (E05-04).

The graph lives in ``workflow_template_versions.definition`` (validated against
``workflow.graph.v1``). ``workflow_graph_nodes`` / ``_edges`` are a flattened,
queryable projection of it — this module keeps them in sync. Deterministic:
the same definition always produces the same rows, in key order.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from bbz_core.domain.workflow import derive_index
from bbz_core.infra.models.workflow import WorkflowGraphEdge, WorkflowGraphNode


async def rebuild_graph_index(
    session: AsyncSession,
    *,
    template_version_id: uuid.UUID,
    definition: dict[str, Any],
) -> tuple[int, int]:
    """Validate ``definition`` and replace this version's node/edge index rows.

    Runs in the caller's transaction. Returns ``(node_count, edge_count)``.
    """
    graph = derive_index(definition)

    await session.execute(
        delete(WorkflowGraphNode).where(
            WorkflowGraphNode.template_version_id == template_version_id
        )
    )
    await session.execute(
        delete(WorkflowGraphEdge).where(
            WorkflowGraphEdge.template_version_id == template_version_id
        )
    )
    await session.flush()

    session.add_all(
        WorkflowGraphNode(
            template_version_id=template_version_id,
            node_key=n.key,
            node_type=n.type,
            function_kind=n.function_kind,
            connector_type=n.connector_type,
            connector_direction=n.connector_direction,
            label=n.label,
            props=n.props,
        )
        for n in graph.nodes
    )
    session.add_all(
        WorkflowGraphEdge(
            template_version_id=template_version_id,
            edge_key=e.key,
            from_node_key=e.from_key,
            to_node_key=e.to_key,
            branch_label=e.branch,
            condition=e.condition,
        )
        for e in graph.edges
    )
    await session.flush()
    return len(graph.nodes), len(graph.edges)
