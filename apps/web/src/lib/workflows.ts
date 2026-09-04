import { api } from '@/lib/apiClient';

/** Workflow-template admin API (Epic 05 — E05-13, MASTER_PROMPT §33).
 *  `definition` is a `workflow.graph.v1` object. All calls are
 *  `workflows.manage_templates`-gated server-side; reads need `workflows.view`. */

export type NodeType = 'event' | 'function' | 'connector';
export type FunctionKind =
  | 'manual'
  | 'confirmation'
  | 'documentation'
  | 'integration_action'
  | 'notification'
  | 'timer'
  | 'event_update';
export type ConnectorKind = 'and' | 'or' | 'xor';
export type ConnectorDir = 'split' | 'join';
export type Lifecycle = 'draft' | 'validated' | 'published' | 'deprecated';

export const FUNCTION_KINDS: FunctionKind[] = [
  'manual',
  'confirmation',
  'documentation',
  'integration_action',
  'notification',
  'timer',
  'event_update',
];
export const CONNECTOR_KINDS: ConnectorKind[] = ['and', 'or', 'xor'];

export interface WfNode {
  key: string;
  type: NodeType;
  label?: string;
  kind?: FunctionKind;
  connector?: ConnectorKind;
  direction?: ConnectorDir;
  props?: Record<string, unknown>;
}

export interface WfEdge {
  key: string;
  from: string;
  to: string;
  branch?: string;
  condition?: Record<string, unknown>;
}

export interface WfGraph {
  start: string;
  nodes: WfNode[];
  edges: WfEdge[];
}

export interface WfTemplate {
  id: string;
  key: string;
  name: string;
}

export interface WfTemplateDetail extends WfTemplate {
  versions: { id: string; version_no: number; lifecycle: Lifecycle }[];
}

export interface WfVersion {
  id: string;
  template_id: string;
  version_no: number;
  lifecycle: Lifecycle;
  definition: WfGraph;
  changelog: string | null;
}

export interface WfIssue {
  code: string;
  message: string;
  node_key: string | null;
}

export interface WfValidateResult {
  valid: boolean;
  lifecycle: Lifecycle;
  issues: WfIssue[];
}

export const emptyGraph = (): WfGraph => ({
  start: 'start',
  nodes: [{ key: 'start', type: 'event', label: 'Start' }],
  edges: [],
});

export const workflowsApi = {
  list: () => api.get<WfTemplate[]>('/workflow-templates'),

  create: (key: string, name: string) =>
    api.post<WfTemplate>('/workflow-templates', { key, name }),

  detail: (id: string) => api.get<WfTemplateDetail>(`/workflow-templates/${id}`),

  rename: (id: string, name: string) =>
    api.patch<WfTemplate>(`/workflow-templates/${id}`, { name }),

  addVersion: (templateId: string, definition: WfGraph, changelog?: string) =>
    api.post<WfVersion>(`/workflow-templates/${templateId}/versions`, {
      definition,
      changelog: changelog ?? null,
    }),

  version: (versionId: string) => api.get<WfVersion>(`/workflow-template-versions/${versionId}`),

  editVersion: (versionId: string, definition: WfGraph, changelog?: string) =>
    api.patch<WfVersion>(`/workflow-template-versions/${versionId}`, {
      definition,
      changelog: changelog ?? null,
    }),

  deleteVersion: (versionId: string) =>
    api.del(`/workflow-template-versions/${versionId}`),

  validate: (versionId: string) =>
    api.post<WfValidateResult>(`/workflow-template-versions/${versionId}/validate`),

  publish: (versionId: string, changelog: string) =>
    api.post<WfVersion>(`/workflow-template-versions/${versionId}/publish`, { changelog }),

  deprecate: (versionId: string) =>
    api.post<WfVersion>(`/workflow-template-versions/${versionId}/deprecate`),
};

/** EPK canvas geometry (E07-19 / #129). Every node occupies the same `NODE_W` ×
 *  `NODE_H` bounding box regardless of shape — a hexagon (event), a rounded
 *  rect (function) or a small circle (connector) — so the vertical layout and
 *  the edge anchors stay shape-agnostic. `GRID` is the drag/keyboard-nudge
 *  snap increment. */
export const NODE_W = 150;
export const NODE_H = 48;
export const GRID = 16;
export const CANVAS_PADDING = 24;
const ROW_GAP = 110;
const COL_GAP = 190;

export const CONNECTOR_GLYPH: Record<ConnectorKind, string> = { and: '∧', or: '∨', xor: '⊕' };

/** Vertical EPK auto-layout: BFS longest-path depth from `start` along edges
 *  gives each node's row (`y`); nodes sharing a row are spread on `x`, centred
 *  on the tree midpoint. Pixel coordinates (top-left of the node's bounding
 *  box) — the fallback `nodePos()` uses for any node without a stored
 *  `props.x`/`props.y`. Deterministic for a given graph. */
export function layoutRows(graph: WfGraph): Map<string, { x: number; y: number }> {
  const byKey = new Map(graph.nodes.map((n) => [n.key, n]));
  const out = new Map<string, string[]>();
  for (const n of graph.nodes) out.set(n.key, []);
  for (const e of graph.edges) if (byKey.has(e.from) && byKey.has(e.to)) out.get(e.from)!.push(e.to);

  const depth = new Map<string, number>();
  const queue: string[] = [graph.start].filter((k) => byKey.has(k));
  depth.set(graph.start, 0);
  const seen = new Set(queue);
  while (queue.length) {
    const k = queue.shift()!;
    for (const next of out.get(k) ?? []) {
      const d = (depth.get(k) ?? 0) + 1;
      if (!depth.has(next) || d > depth.get(next)!) depth.set(next, d);
      if (!seen.has(next)) {
        seen.add(next);
        queue.push(next);
      }
    }
  }

  const rows = new Map<number, string[]>();
  for (const n of graph.nodes) {
    if (!depth.has(n.key)) depth.set(n.key, 0);
    const d = depth.get(n.key)!;
    if (!rows.has(d)) rows.set(d, []);
    rows.get(d)!.push(n.key);
  }

  // Centre-x per node first (node midpoints, tree centred on 0), then shift
  // everything into a positive top-left coordinate space.
  const centerX = new Map<string, number>();
  for (const keys of rows.values()) {
    const span = (keys.length - 1) * COL_GAP;
    keys.forEach((key, i) => centerX.set(key, i * COL_GAP - span / 2));
  }
  let minLeft = 0;
  for (const cx of centerX.values()) minLeft = Math.min(minLeft, cx - NODE_W / 2);

  const pos = new Map<string, { x: number; y: number }>();
  for (const n of graph.nodes) {
    const d = depth.get(n.key)!;
    const cx = centerX.get(n.key)!;
    pos.set(n.key, {
      x: cx - NODE_W / 2 - minLeft + CANVAS_PADDING,
      y: d * ROW_GAP + CANVAS_PADDING,
    });
  }
  return pos;
}

/** A node's canvas position: its stored `props.x`/`props.y` when both are
 *  finite numbers, else the auto-layout fallback. */
export function nodePos(
  node: WfNode,
  auto: Map<string, { x: number; y: number }>,
): { x: number; y: number } {
  const x = node.props?.x;
  const y = node.props?.y;
  if (typeof x === 'number' && Number.isFinite(x) && typeof y === 'number' && Number.isFinite(y)) {
    return { x, y };
  }
  return auto.get(node.key) ?? { x: CANVAS_PADDING, y: CANVAS_PADDING };
}

/** Snap a coordinate to the drag/keyboard grid. */
export function snap(v: number, grid: number = GRID): number {
  return Math.round(v / grid) * grid;
}

/** Pure drag/nudge math: current position + delta, snapped, clamped onto the
 *  canvas. The caller (pointer or keyboard handler) writes the result into
 *  `node.props`. */
export function applyNodeDrag(
  node: WfNode,
  dx: number,
  dy: number,
  auto: Map<string, { x: number; y: number }>,
): { x: number; y: number } {
  const base = nodePos(node, auto);
  return { x: Math.max(0, snap(base.x + dx)), y: Math.max(0, snap(base.y + dy)) };
}

/** Where a control-flow arrow meets a node's shape. Every shape (hexagon,
 *  rounded rect, connector circle) shares the same `NODE_W`×`NODE_H` bounding
 *  box and presents a flat top/bottom edge, so the anchor is shape-agnostic:
 *  top-centre for an incoming arrow, bottom-centre for an outgoing one. */
export function anchorFor(
  pos: { x: number; y: number },
  side: 'in' | 'out',
): { x: number; y: number } {
  const cx = pos.x + NODE_W / 2;
  return side === 'in' ? { x: cx, y: pos.y } : { x: cx, y: pos.y + NODE_H };
}
