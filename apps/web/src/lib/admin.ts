import { api } from '@/lib/apiClient';

/**
 * The Administration sub-sections in nav order, each with the permission that
 * gates it (#721). `AdminPage` renders the ones the user holds; the router
 * guard redirects an unauthorized deep link to the first one they do.
 */
export const ADMIN_SECTIONS = [
  { name: 'admin-instance', key: 'instance', perm: 'system.settings.manage' },
  { name: 'admin-users', key: 'users', perm: 'users.manage' },
  { name: 'admin-directory', key: 'directory', perm: 'system.settings.manage' },
  { name: 'admin-integrations', key: 'integrations', perm: 'integrations.view' },
  { name: 'admin-telephony', key: 'telephony', perm: 'integrations.configure' },
  { name: 'workflow-admin', key: 'workflows', perm: 'workflows.manage_templates' },
  { name: 'admin-triggers', key: 'triggers', perm: 'technical_endpoints.manage' },
  { name: 'admin-endpoints', key: 'endpoints', perm: 'technical_endpoints.manage' },
  { name: 'admin-system', key: 'system', perm: 'system.cluster.view' },
] as const;

/** true when the user may see the Administration area at all. */
export function canSeeAdmin(can: (perm: string) => boolean): boolean {
  return ADMIN_SECTIONS.some((s) => can(s.perm));
}

/** Where the effective value of a runtime setting comes from (ADR-0031). */
export type SettingSource = 'database' | 'environment' | 'default';

export type SettingValue = string | number | boolean | string[] | null;

export interface AdminSetting {
  key: string;
  name: string;
  label: string;
  help: string;
  kind: 'str' | 'bool' | 'int' | 'str_list';
  secret: boolean;
  /** effective value; `null` for a secret (see `configured`) */
  value: SettingValue;
  /** for a secret key: whether a value is available from the environment */
  configured: boolean | null;
  source: SettingSource;
  overridden: boolean;
}

export interface AdminSettingGroup {
  group: string;
  label: string;
  items: AdminSetting[];
}

export interface AdminSettingsResponse {
  groups: AdminSettingGroup[];
}

export interface AdminSettingsUpdateResponse {
  updated: string[];
  groups: AdminSettingGroup[];
}

export interface IntegrationAdapter {
  id: string;
  name: string;
  mock: boolean;
  version: string;
}

export interface DomainIntegration {
  domain: string;
  setting_key: string;
  active_id: string;
  source: SettingSource;
  available: IntegrationAdapter[];
  active_is_mock: boolean;
  health: { state: string; summary: string } | null;
}

/** SIP (Asterisk / ARI) gateway config (E13-07, ADR-0033). The ARI password is
 * write-only — the API returns `ari_password_configured`, never the value. */
export interface SipGateway {
  instance_id: string;
  kind: string;
  host: string;
  port: number;
  tls: boolean;
  app_name: string;
  dtmf_transport: 'rfc2833' | 'sip_info';
  ari_username: string;
  ari_password_configured: boolean;
  enabled: boolean;
  created_at: string | null;
  updated_at: string | null;
}

export interface SipLine {
  bbz_line_id: string;
  asterisk_endpoint: string;
  label: string;
  enabled: boolean;
}

export interface SipConfig {
  gateway: SipGateway;
  lines: SipLine[];
  /** whether `telephony_sip` is the selected telephony provider */
  active: boolean;
}

export interface SipGatewayInput {
  host: string;
  port: number;
  tls: boolean;
  app_name: string;
  dtmf_transport: 'rfc2833' | 'sip_info';
  ari_username: string;
  /** omit to keep the stored password; a value replaces it */
  ari_password?: string;
  enabled: boolean;
}

export interface SipProbeResult {
  reachable: boolean;
  detail: string;
  asterisk_version: string | null;
}

export const adminApi = {
  /** `GET /api/v1/admin/settings` — every overridable key, grouped. */
  settings: (signal?: AbortSignal) =>
    api.get<AdminSettingsResponse>('/admin/settings', { signal }),

  /** `PUT /api/v1/admin/settings/{group}` — write the overrides for one group. */
  updateSettings: (group: string, values: Record<string, SettingValue>) =>
    api.put<AdminSettingsUpdateResponse>(`/admin/settings/${group}`, { values }),

  /** `GET /api/v1/admin/integrations` — provider per domain + health (#724). */
  integrations: (signal?: AbortSignal) =>
    api.get<{ domains: DomainIntegration[] }>('/admin/integrations', { signal }),

  /** `GET /api/v1/admin/telephony/sip` — the SIP gateway config + lines. */
  sipConfig: (signal?: AbortSignal) =>
    api.get<SipConfig>('/admin/telephony/sip', { signal }),

  /** `PUT /api/v1/admin/telephony/sip` — set the gateway (password write-only). */
  putSipGateway: (body: SipGatewayInput) => api.put<SipConfig>('/admin/telephony/sip', body),

  /** `PUT /api/v1/admin/telephony/sip/lines/{id}` — add or update a line. */
  putSipLine: (id: string, body: { asterisk_endpoint: string | null; label: string; enabled: boolean }) =>
    api.put<SipLine>(`/admin/telephony/sip/lines/${encodeURIComponent(id)}`, body),

  /** `DELETE /api/v1/admin/telephony/sip/lines/{id}`. */
  deleteSipLine: (id: string) =>
    api.del<void>(`/admin/telephony/sip/lines/${encodeURIComponent(id)}`),

  /** `POST /api/v1/admin/telephony/sip/test` — probe the stored gateway. */
  testSipConnection: () => api.post<SipProbeResult>('/admin/telephony/sip/test'),
};
