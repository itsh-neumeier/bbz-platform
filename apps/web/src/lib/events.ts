import { api } from '@/lib/apiClient';

export type EventPriority = 'critical' | 'high' | 'medium' | 'low';
export type EventStatus = 'new' | 'accepted' | 'acknowledged' | 'opened' | 'archived';

export const PRIORITY_RANK: Record<EventPriority, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
};

/** The single lifecycle action available from a given status (MASTER_PROMPT §13). */
export const NEXT_ACTION: Partial<Record<EventStatus, 'accept' | 'acknowledge' | 'open' | 'archive'>> = {
  new: 'accept',
  accepted: 'acknowledge',
  acknowledged: 'open',
  opened: 'archive',
};

export interface EventListItem {
  id: string;
  title: string;
  priority: EventPriority;
  status: EventStatus;
  bbz_id: string | null;
  workplace_id: string | null;
  version: number;
  assignee_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface StatusHistoryEntry {
  from_status: string | null;
  to_status: string;
  changed_at: string;
  changed_by: string | null;
}

export interface EventNote {
  id: string;
  kind: string;
  body: string;
  created_by: string | null;
  created_at: string;
  version: number;
  edited_by?: string | null;
  edited_at?: string | null;
}

export interface EventDetail extends EventListItem {
  description: string | null;
  status_history: StatusHistoryEntry[];
  notes: EventNote[];
}

export interface EventPage {
  items: EventListItem[];
  next_cursor: string | null;
}

export interface PriorityAlert {
  active: boolean;
  events: { id: string; priority: EventPriority; title: string }[];
}

/** One entry of the cross-workplace activity log (MASTER_PROMPT §13.1). */
export interface LogbookEntry {
  event_seq: number;
  event_id: string;
  occurred_at_utc: string;
  event_type: string;
  title: string;
  priority: EventPriority;
  status: EventStatus;
  actor: string | null;
}

export const eventsApi = {
  workQueue: (signal?: AbortSignal) =>
    api.get<EventPage>('/events?queue=active&limit=200', { signal }),

  list: (params: Record<string, string>, signal?: AbortSignal) =>
    api.get<EventPage>('/events?' + new URLSearchParams(params).toString(), { signal }),

  get: (id: string, signal?: AbortSignal) => api.get<EventDetail>(`/events/${id}`, { signal }),

  priorityAlert: (signal?: AbortSignal) =>
    api.get<PriorityAlert>('/events/priority-alert', { signal }),

  /** The cross-workplace activity log — recent lifecycle events, newest first. */
  logbook: (limit = 40, signal?: AbortSignal) =>
    api.get<{ items: LogbookEntry[] }>(`/events/logbook?limit=${limit}`, { signal }),

  /** Returns the minimal `EventOut` (id/title/priority/status/version/…). */
  transition: (id: string, action: 'accept' | 'acknowledge' | 'open' | 'archive', version: number) =>
    api.post<{
      id: string;
      title: string;
      description: string | null;
      priority: EventPriority;
      status: EventStatus;
      bbz_id: string | null;
      workplace_id: string | null;
      version: number;
    }>(`/events/${id}/${action}`, undefined, { expectedVersion: version }),

  addNote: (id: string, body: string, kind: 'work' | 'postprocess' = 'work') =>
    api.post<{ note_id: string; event_seq: number }>(`/events/${id}/notes`, { body, kind }),

  editNote: (id: string, noteId: string, body: string) =>
    api.patch<{ note_id: string; event_seq: number }>(`/events/${id}/notes/${noteId}`, { body }),

  takeover: (id: string, version: number) =>
    api.post<EventListItem>(`/events/${id}/takeover`, undefined, { expectedVersion: version }),

  assign: (id: string, targetUserId: string, version: number) =>
    api.post<EventListItem>(`/events/${id}/assign`, { target_user_id: targetUserId }, {
      expectedVersion: version,
    }),

  reactivationIntent: (id: string) =>
    api.post<{ token: string; expires_at: string; event_version: number }>(
      `/events/${id}/reactivation-intent`,
    ),

  reactivate: (id: string, token: string, reason: string, version: number) =>
    api.post<EventListItem>(
      `/events/${id}/reactivate`,
      { confirm: true, reason, token },
      { expectedVersion: version },
    ),

  workflow: (id: string, signal?: AbortSignal) =>
    api.get<WorkflowInstance>(`/events/${id}/workflow`, { signal }),

  completeStep: (id: string, nodeKey: string, result: Record<string, unknown> = {}) =>
    api.post<WorkflowInstance>(
      `/events/${id}/workflow/steps/${encodeURIComponent(nodeKey)}/complete`,
      { result },
    ),

  decide: (id: string, connectorKey: string, chosen: string[]) =>
    api.post<WorkflowInstance>(
      `/events/${id}/workflow/decisions/${encodeURIComponent(connectorKey)}`,
      { chosen },
    ),

  /** active users an event may be handed to (E07-10 / #111) */
  assignable: (signal?: AbortSignal) =>
    api.get<{ users: { id: string; display_name: string }[] }>('/events/assignable', { signal }),

  archiveDetail: (id: string, signal?: AbortSignal) =>
    api.get<ArchiveDetail>(`/events/${id}/archive-detail`, { signal }),

  archivedList: (params: Record<string, string> = {}, signal?: AbortSignal) =>
    api.get<EventPage>(
      '/events?' + new URLSearchParams({ include_archived: 'true', status: 'archived', ...params }),
      { signal },
    ),

  streamHead: () => api.get<{ last_seq: number }>('/events/stream/head'),
};

export interface WorkflowStep {
  node_key: string;
  kind: string | null;
  label: string | null;
  /** `done` = completed · `active` = a token is waiting here (act now) · `pending` = not yet reached */
  state: 'done' | 'active' | 'pending';
  completed_at?: string;
  completed_by?: string | null;
}

export interface PendingDecision {
  connector_node_key: string;
  connector_type: string;
  options: { edge_key: string; to: string; branch: string | null; has_condition: boolean }[];
}

export interface WorkflowDecision {
  connector_node_key: string;
  chosen_branches: string[];
  auto: boolean;
  decided_by: string | null;
  decided_at: string;
}

/** `GET /events/{id}/workflow` — mirrors the engine's token state (returns 404 when there is no instance). */
export interface WorkflowInstance {
  instance_id: string;
  event_id: string;
  status: string;
  started_at: string;
  ended_at: string | null;
  template: { key: string | null; version_no: number };
  progress: { done: number; total: number };
  steps: WorkflowStep[];
  pending_decisions: PendingDecision[];
  decisions: WorkflowDecision[];
}

export interface ArchiveDetail {
  event: EventDetail;
  domain_events: { event_seq: number; event_type: string; occurred_at_utc: string }[];
  workflows: WorkflowInstance[];
  audit_refs: { id: string; action: string; occurred_at_utc: string; correlation_id: string | null }[];
  calls: unknown[];
}
