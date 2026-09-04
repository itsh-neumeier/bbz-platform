import { api } from '@/lib/apiClient';

export interface DirectoryTestResult {
  configured: boolean;
  reachable: boolean;
  tls_ok: boolean;
  bind_ok: boolean;
  sample_count: number | null;
  error: string | null;
}

export interface GroupMapping {
  id: string;
  provider: string;
  external_group: string;
  role_key: string;
}

export interface SyncReport {
  source: string;
  ok: boolean;
  dry_run: boolean;
  aborted: boolean;
  error: string | null;
  scanned: number;
  created: number;
  deactivated: number;
  errors: string[];
  created_uids: string[];
  deactivated_uids: string[];
}

export interface SyncState {
  source: string;
  last_run_at: string | null;
  last_success_at: string | null;
  last_error: string | null;
  last_summary: Record<string, unknown> | null;
}

export const directoryApi = {
  test: () => api.post<DirectoryTestResult>('/admin/directory/test'),
  syncState: (signal?: AbortSignal) =>
    api.get<SyncState>('/auth/directory-sync/state', { signal }),
  runSync: (dryRun: boolean) =>
    api.post<SyncReport>('/auth/directory-sync', { dry_run: dryRun }),
};

export const groupMappingsApi = {
  list: (provider: string, signal?: AbortSignal) =>
    api.get<{ mappings: GroupMapping[] }>(`/auth/group-mappings?provider=${provider}`, { signal }),
  create: (provider: string, externalGroup: string, roleKey: string) =>
    api.post<GroupMapping>('/auth/group-mappings', {
      provider,
      external_group: externalGroup,
      role_key: roleKey,
    }),
  remove: (id: string) => api.del<void>(`/auth/group-mappings/${id}`),
};
