import { api } from '@/lib/apiClient';

export interface MonitorInput {
  key: string;
  label: string;
}
export interface MonitorOutput {
  key: string;
  label: string;
  grid_row: number | null;
  grid_col: number | null;
  is_large_display: boolean;
  is_fixed: boolean;
}
export interface MonitorRoute {
  output_key: string;
  input_key: string;
  is_fixed: boolean;
  set_at: string;
}
export interface MonitorRoutes {
  inputs: MonitorInput[];
  outputs: MonitorOutput[];
  routes: MonitorRoute[];
  provider_available: boolean;
  provider_healthy: boolean;
}
export interface MonitorProfile {
  id: string;
  name: string;
  scope: 'user' | 'workplace';
  workplace_id: string | null;
  layout: Record<string, string>;
}

export const monitorApi = {
  routes: (signal?: AbortSignal) => api.get<MonitorRoutes>('/monitor/routes', { signal }),

  setRoutes: (assignments: Record<string, string>) =>
    api.put<MonitorRoutes>('/monitor/routes', { assignments }),

  resetStandard: () => api.post<MonitorRoutes>('/monitor/routes/reset-standard'),

  profiles: () => api.get<{ profiles: MonitorProfile[] }>('/monitor/profiles'),

  saveProfile: (name: string, layout: Record<string, string>, scope: 'user' | 'workplace' = 'user') =>
    api.post<MonitorProfile>('/monitor/profiles', { name, scope, layout }),

  applyProfile: (id: string) => api.post<MonitorRoutes>(`/monitor/profiles/${id}/apply`),

  deleteProfile: (id: string) => api.del(`/monitor/profiles/${id}`),
};
