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
  /** MoH file ids (#817); null = no music */
  ring_moh_file_id: string | null;
  hold_moh_file_id: string | null;
}

/** an uploaded music-on-hold WAV (#817) */
export interface SipMohFile {
  id: string;
  name: string;
  original_filename: string;
  mime: string;
  size_bytes: number;
  sha256: string;
  uploaded_at: string;
  /** bbz_line_ids that use this file — non-empty ⇒ not deletable */
  used_by: string[];
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

// --- SIP trunks (ITSP) — ADR-0034 -----------------------------------------

export type SipTrunkProvider = 'leonet' | 'telekom' | 'generic';
export type SipTrunkTransport = 'udp' | 'tcp' | 'tls';
export type SipTrunkDtmfMode = 'rfc4733' | 'inband' | 'info' | 'auto';

export interface SipTrunk {
  trunk_id: string;
  provider: SipTrunkProvider;
  display_name: string;
  enabled: boolean;
  sip_server: string;
  sip_port: number;
  transport: SipTrunkTransport;
  outbound_proxy: string;
  from_domain: string;
  registration: boolean;
  auth_username: string;
  auth_password_configured: boolean;
  match_hosts: string;
  codecs: string;
  dtmf_mode: SipTrunkDtmfMode;
  caller_id_e164: string;
}

export interface SipNumber {
  e164: string;
  trunk_id: string;
  bbz_line_id: string;
  label: string;
  registration: boolean;
  auth_username: string;
  auth_password_configured: boolean;
  enabled: boolean;
}

export interface SipTrunksResponse {
  trunks: SipTrunk[];
  numbers: SipNumber[];
}

/** `PUT .../trunks/{id}` body — `auth_password` write-only (omit to keep). */
export type SipTrunkInput = Omit<SipTrunk, 'trunk_id' | 'auth_password_configured'> & {
  auth_password?: string;
};

/** `PUT .../numbers/{e164}` body — `auth_password` write-only (omit to keep). */
export type SipNumberInput = Omit<SipNumber, 'e164' | 'auth_password_configured'> & {
  auth_password?: string;
};

export interface SipTrunkProbeResult {
  /** online | loaded | not_loaded | unreachable */
  state: string;
  detail: string;
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
  putSipLine: (
    id: string,
    body: {
      asterisk_endpoint: string | null;
      label: string;
      enabled: boolean;
      ring_moh_file_id?: string | null;
      hold_moh_file_id?: string | null;
    },
  ) => api.put<SipLine>(`/admin/telephony/sip/lines/${encodeURIComponent(id)}`, body),

  /** `DELETE /api/v1/admin/telephony/sip/lines/{id}`. */
  deleteSipLine: (id: string) =>
    api.del<void>(`/admin/telephony/sip/lines/${encodeURIComponent(id)}`),

  // --- music on hold (#817) ---------------------------------------------

  /** `GET /api/v1/admin/telephony/moh` — every uploaded MoH file. */
  sipMohFiles: (signal?: AbortSignal) =>
    api.get<{ files: SipMohFile[] }>('/admin/telephony/moh', { signal }),

  /** `POST /api/v1/admin/telephony/moh` — raw `audio/wav` body + `?name=`. */
  uploadSipMoh: (name: string, file: File) =>
    api.postBlob<SipMohFile>(
      `/admin/telephony/moh?name=${encodeURIComponent(name)}&filename=${encodeURIComponent(file.name)}`,
      file,
    ),

  /** `DELETE /api/v1/admin/telephony/moh/{id}` — 409 while a line uses it. */
  deleteSipMoh: (id: string) =>
    api.del<void>(`/admin/telephony/moh/${encodeURIComponent(id)}`),

  /** `POST /api/v1/admin/telephony/sip/test` — probe the stored gateway. */
  testSipConnection: () => api.post<SipProbeResult>('/admin/telephony/sip/test'),

  // --- SIP trunks (ITSP) — ADR-0034 ---------------------------------------

  /** `GET .../sip/trunks` — every trunk + every public number. */
  sipTrunks: (signal?: AbortSignal) =>
    api.get<SipTrunksResponse>('/admin/telephony/sip/trunks', { signal }),

  /** `PUT .../sip/trunks/{id}` — add or update a trunk (password write-only). */
  putSipTrunk: (id: string, body: SipTrunkInput) =>
    api.put<SipTrunk>(`/admin/telephony/sip/trunks/${encodeURIComponent(id)}`, body),

  /** `DELETE .../sip/trunks/{id}` — also cascades its numbers. */
  deleteSipTrunk: (id: string) =>
    api.del<void>(`/admin/telephony/sip/trunks/${encodeURIComponent(id)}`),

  /** `PUT .../sip/numbers/{e164}` — add or update a public number. */
  putSipNumber: (e164: string, body: SipNumberInput) =>
    api.put<SipNumber>(`/admin/telephony/sip/numbers/${encodeURIComponent(e164)}`, body),

  /** `DELETE .../sip/numbers/{e164}`. */
  deleteSipNumber: (e164: string) =>
    api.del<void>(`/admin/telephony/sip/numbers/${encodeURIComponent(e164)}`),

  /** `GET .../sip/asterisk-config` — the generated PJSIP + dialplan text. */
  sipAsteriskConfig: (part: 'all' | 'pjsip' | 'extensions' = 'all') =>
    api.getText(`/admin/telephony/sip/asterisk-config?part=${part}`),

  /** `POST .../sip/trunks/{id}/test` — is the endpoint loaded in Asterisk? */
  testSipTrunk: (id: string) =>
    api.post<SipTrunkProbeResult>(`/admin/telephony/sip/trunks/${encodeURIComponent(id)}/test`),
};
