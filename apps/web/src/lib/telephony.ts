import { api } from '@/lib/apiClient';

/** Telephony / call-control API (Epic 11 — E11-06/07/09/11/12, MASTER_PROMPT §13.8–13.11). */

export type CallState =
  | 'offered'
  | 'ringing'
  | 'connected'
  | 'held'
  | 'transferring'
  | 'disconnected'
  | 'failed'
  | 'ended_pending_documentation';

export type CallDirection = 'inbound' | 'outbound';
export type CallerPriority = 'low' | 'medium' | 'high';

export type CallCategory =
  | 'information_request'
  | 'technical_fault'
  | 'cleaning_report_customer'
  | 'evu_evi_notice'
  | 'other';

export const CALL_CATEGORIES: CallCategory[] = [
  'information_request',
  'technical_fault',
  'cleaning_report_customer',
  'evu_evi_notice',
  'other',
];

export interface CallParticipant {
  number: string | null;
  display_name: string | null;
  role: string;
}

export interface Call {
  id: string;
  bbz_call_id: string;
  provider: string;
  direction: CallDirection;
  state: CallState;
  line_id: string | null;
  workplace_id: string | null;
  started_at: string | null;
  ended_at: string | null;
  created_at: string;
  category: CallCategory | null;
  has_free_text: boolean;
  caller_contact_id: string | null;
  caller_priority: CallerPriority | null;
  participants: CallParticipant[];
}

export interface CallPage {
  items: Call[];
  next_cursor: string | null;
}

export interface ControlResult {
  call_id: string | null;
  action: string;
  accepted: boolean;
  detail: string | null;
}

export interface CallDocumentation {
  call_id: string;
  category: CallCategory | null;
  free_text: string | null;
  documented_by: string | null;
  documented_at: string | null;
  mandatory_done: boolean;
}

export interface Line {
  id: string;
  provider: string;
  external_id: string;
  label: string | null;
  state: string;
  workplace_id: string | null;
  updated_at: string;
}

export const PRIORITY_RANK: Record<string, number> = { high: 0, medium: 1, low: 2, unknown: 3 };

/** the "other party" on a call, for display (caller on inbound, callee on outbound). */
export function otherParty(call: Call): string {
  const wantRole = call.direction === 'inbound' ? 'caller' : 'callee';
  const p = call.participants.find((x) => x.role === wantRole) ?? call.participants[0];
  return p?.display_name ?? p?.number ?? '—';
}

export const telephonyApi = {
  ringing: (signal?: AbortSignal) => api.get<CallPage>('/calls/ringing', { signal }),

  history: (
    params: { limit?: number; number?: string; direction?: CallDirection } = {},
    signal?: AbortSignal,
  ) => {
    const qs = new URLSearchParams();
    if (params.limit) qs.set('limit', String(params.limit));
    if (params.number) qs.set('number', params.number);
    if (params.direction) qs.set('direction', params.direction);
    const tail = qs.toString();
    return api.get<CallPage>(`/calls${tail ? `?${tail}` : ''}`, { signal });
  },

  lines: (signal?: AbortSignal) => api.get<{ lines: Line[] }>('/lines', { signal }),

  dial: (line_id: string, destination: string) =>
    api.post<{ accepted: boolean; detail: string | null }>('/calls/dial', { line_id, destination }),

  answer: (id: string) => api.post<ControlResult>(`/calls/${id}/answer`),
  hangup: (id: string) => api.post<ControlResult>(`/calls/${id}/hangup`),
  hold: (id: string) => api.post<ControlResult>(`/calls/${id}/hold`),
  resume: (id: string) => api.post<ControlResult>(`/calls/${id}/resume`),
  transfer: (id: string, destination: string) =>
    api.post<ControlResult>(`/calls/${id}/transfer`, { destination }),

  getDoc: (id: string, signal?: AbortSignal) =>
    api.get<CallDocumentation>(`/calls/${id}/documentation`, { signal }),
  putDoc: (id: string, body: { category: CallCategory | null; free_text: string | null }) =>
    api.put<CallDocumentation>(`/calls/${id}/documentation`, body),

  pendingDocs: (signal?: AbortSignal) =>
    api.get<{ calls: { call_id: string; bbz_call_id: string; direction: string; ended_at: string | null }[] }>(
      '/calls/pending-documentation',
      { signal },
    ),
};
