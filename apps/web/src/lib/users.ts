import { api } from '@/lib/apiClient';

export interface AdminUser {
  id: string;
  display_name: string;
  status: string;
  external_ref: string | null;
  roles: string[];
  providers: string[];
}

export interface CreateUserBody {
  display_name: string;
  local_username?: string | null;
  initial_password?: string | null;
  external_ref?: string | null;
}

export interface Role {
  id: string;
  key: string;
  name: string;
  builtin: boolean;
}

export interface Revoked {
  sessions_revoked: number;
}

export interface MfaPolicy {
  role_key: string;
  grace_period_days: number;
}

export const usersApi = {
  list: (signal?: AbortSignal) =>
    api.get<AdminUser[]>('/users?include_disabled=true', { signal }),
  get: (id: string) => api.get<AdminUser>(`/users/${id}`),
  create: (body: CreateUserBody) => api.post<AdminUser>('/users', body),
  update: (id: string, body: { display_name?: string; external_ref?: string | null }) =>
    api.patch<AdminUser>(`/users/${id}`, body),
  activate: (id: string) => api.post<AdminUser>(`/users/${id}/activate`),
  deactivate: (id: string) => api.post<Revoked>(`/users/${id}/deactivate`),
  resetPassword: (id: string, newPassword: string) =>
    api.post<Revoked>(`/users/${id}/password-reset`, { new_password: newPassword }),
};

export const rolesApi = {
  list: (signal?: AbortSignal) => api.get<Role[]>('/roles', { signal }),
  assign: (userId: string, roleId: string) =>
    api.post<void>(`/users/${userId}/roles`, { role_id: roleId }),
  revoke: (userId: string, roleId: string) =>
    api.del<void>(`/users/${userId}/roles/${roleId}`),
};

export const mfaPoliciesApi = {
  list: (signal?: AbortSignal) =>
    api.get<{ policies: MfaPolicy[] }>('/auth/mfa-policies', { signal }),
  set: (roleKey: string, gracePeriodDays: number) =>
    api.put<MfaPolicy>(`/auth/mfa-policies/${roleKey}`, { grace_period_days: gracePeriodDays }),
  remove: (roleKey: string) => api.del<void>(`/auth/mfa-policies/${roleKey}`),
};
