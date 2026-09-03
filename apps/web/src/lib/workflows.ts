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

/** Deterministic column layout: BFS depth from `start` along edges. Nodes with
 *  no inbound edge that aren't the start sit in column 0 too. */
export function layoutColumns(graph: WfGraph): Map<string, { col: number; row: number }> {
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
  let maxDepth = 0;
  for (const n of graph.nodes) {
    if (!depth.has(n.key)) depth.set(n.key, 0);
    maxDepth = Math.max(maxDepth, depth.get(n.key)!);
  }
  const rowOf = new Map<number, number>();
  const pos = new Map<string, { col: number; row: number }>();
  for (const n of graph.nodes) {
    const col = depth.get(n.key) ?? 0;
    const row = rowOf.get(col) ?? 0;
    rowOf.set(col, row + 1);
    pos.set(n.key, { col, row });
  }
  return pos;
}
