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
};
