import { api } from '@/lib/apiClient';

// --- technical endpoints (§14) -------------------------------------------

export const ENDPOINT_TYPES = [
  'door_station',
  'bma',
  'panic_button',
  'video_alarm',
  'alarm_dialer',
  'custom',
] as const;
export const PRIORITIES = ['critical', 'high', 'medium', 'low'] as const;

export interface TechnicalEndpoint {
  id: string;
  name: string;
  type: string;
  site: string | null;
  provider_id: string | null;
  external_source_ids: string[];
  default_priority: string | null;
  enabled: boolean;
  active_config_version: number;
}

export interface EndpointBody {
  name: string;
  type: string;
  site?: string | null;
  provider_id?: string | null;
  default_priority?: string | null;
  enabled?: boolean;
}

export const technicalEndpointsApi = {
  list: (signal?: AbortSignal) => api.get<TechnicalEndpoint[]>('/technical-endpoints', { signal }),
  create: (body: EndpointBody) => api.post<TechnicalEndpoint>('/technical-endpoints', body),
  update: (id: string, body: Partial<EndpointBody>) =>
    api.patch<TechnicalEndpoint>(`/technical-endpoints/${id}`, body),
  remove: (id: string) => api.del<void>(`/technical-endpoints/${id}`),
};

// --- trigger rules (§32, E15) ------------------------------------------

export interface TriggerRuleVersion {
  id: string;
  rule_id: string;
  version_no: number;
  lifecycle: string;
  conditions: Record<string, unknown>;
  actions: unknown[];
  changelog: string | null;
}

export interface TriggerRule {
  id: string;
  name: string;
  priority: number;
  endpoint_id: string | null;
  lifecycle: string;
}

export interface TriggerRuleDetail extends TriggerRule {
  versions: TriggerRuleVersion[];
}

export interface SimulationResult {
  signal_type: string;
  executed: boolean;
  planned_action_count: number;
  matched: {
    rule_id: string;
    rule_name: string;
    priority: number;
    version_id: string;
    version_no: number;
    actions: Record<string, unknown>[];
  }[];
}

export const triggerRulesApi = {
  list: (signal?: AbortSignal) => api.get<TriggerRule[]>('/trigger-rules', { signal }),
  get: (id: string) => api.get<TriggerRuleDetail>(`/trigger-rules/${id}`),
  create: (body: {
    name: string;
    priority: number;
    endpoint_id?: string | null;
    conditions?: Record<string, unknown>;
    actions?: Record<string, unknown>[];
  }) => api.post<TriggerRuleDetail>('/trigger-rules', body),
  remove: (id: string) => api.del<void>(`/trigger-rules/${id}`),
  validate: (versionId: string) =>
    api.post<{ valid: boolean; lifecycle: string; issues: string[] }>(
      `/trigger-rule-versions/${versionId}/validate`,
    ),
  publish: (versionId: string, changelog?: string) =>
    api.post<TriggerRuleVersion>(`/trigger-rule-versions/${versionId}/publish`, { changelog }),
  retire: (versionId: string) =>
    api.post<TriggerRuleVersion>(`/trigger-rule-versions/${versionId}/retire`),
  simulate: (signal: Record<string, unknown>) =>
    api.post<SimulationResult>('/trigger-rules/simulate', { signal }),
};
