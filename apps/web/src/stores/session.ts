import { defineStore } from 'pinia';
import { api, ApiError, markAuthenticated } from '@/lib/apiClient';

/** `/api/v1/meta` — backend build + capability info (public). */
export interface Meta {
  service: string;
  version: string;
  api_version: string;
  environment: string;
  node_id: string;
  capabilities: string[];
  known_integrations: string[];
}

export interface User {
  id: string;
  display_name: string;
  status: string;
}

interface LoginResponse {
  user: User;
  must_change_password: boolean;
  csrf_token: string;
  mfa_enrolment_required: boolean;
  mfa_grace_until: string | null;
}

interface MeResponse {
  user: User;
  permissions: string[];
  scopes: string[];
}

export type SecondFactor =
  | { kind: 'none' }
  | { kind: 'totp' }
  | { kind: 'webauthn'; options: unknown };

export interface Credentials {
  username: string;
  password: string;
  totp?: string;
  webauthn?: string;
}

const COMMS_MIN = 280;
const COMMS_MAX = 640;

export const useSessionStore = defineStore('session', {
  state: () => ({
    meta: null as Meta | null,
    user: null as User | null,
    permissions: [] as string[],
    mustChangePassword: false,
    /** set true when a request 401s under an established session. */
    expired: false,
    loading: false,
    commsWidth: readPersistedWidth(),
  }),
  getters: {
    authenticated: (s): boolean => s.user !== null && !s.mustChangePassword,
    can:
      (s) =>
      (perm: string): boolean =>
        s.permissions.includes(perm),
  },
  actions: {
    async loadMeta(): Promise<void> {
      try {
        this.meta = await api.get<Meta>('/meta');
      } catch {
        /* the shell renders without it */
      }
    },

    /**
     * Attempt a login. Returns the required second factor: `none` on success,
     * or `totp` / `webauthn` when the server wants one — call `login` again
     * with the extra field filled in.
     */
    async login(creds: Credentials): Promise<SecondFactor> {
      this.loading = true;
      try {
        const r = await api.post<LoginResponse>('/auth/login', {
          username: creds.username,
          password: creds.password,
          totp: creds.totp ?? null,
          webauthn: creds.webauthn ?? null,
        });
        this.user = r.user;
        this.mustChangePassword = r.must_change_password;
        markAuthenticated(true);
        this.expired = false;
        await this.fetchMe();
        return { kind: 'none' };
      } catch (e) {
        if (e instanceof ApiError && e.code === 'totp_required') return { kind: 'totp' };
        if (e instanceof ApiError && e.code === 'webauthn_required') {
          const d = e.details as { options?: unknown } | null;
          return { kind: 'webauthn', options: d?.options ?? null };
        }
        throw e;
      } finally {
        this.loading = false;
      }
    },

    async fetchMe(): Promise<void> {
      const me = await api.get<MeResponse>('/auth/me');
      this.user = me.user;
      this.permissions = me.permissions;
      markAuthenticated(true);
    },

    /** Silent re-auth from cookies on app start / after a reload. */
    async restore(): Promise<boolean> {
      try {
        await this.fetchMe();
        return true;
      } catch {
        this.reset();
        return false;
      }
    },

    async changePassword(current: string, next: string): Promise<void> {
      await api.post('/auth/password', { current_password: current, new_password: next });
      this.mustChangePassword = false;
    },

    async logout(): Promise<void> {
      try {
        await api.post('/auth/logout');
      } catch {
        /* best effort — cookies are cleared server-side */
      }
      this.reset();
    },

    /** called by the API layer / router when a request 401s mid-session. */
    markExpired(): void {
      this.expired = true;
      this.user = null;
      this.permissions = [];
      markAuthenticated(false);
    },

    reset(): void {
      this.user = null;
      this.permissions = [];
      this.mustChangePassword = false;
      this.expired = false;
      markAuthenticated(false);
    },

    setCommsWidth(px: number): void {
      this.commsWidth = Math.min(COMMS_MAX, Math.max(COMMS_MIN, Math.round(px)));
      try {
        localStorage.setItem('bbz.commsWidth', String(this.commsWidth));
      } catch {
        /* private mode — non-fatal */
      }
    },
  },
});

function readPersistedWidth(): number {
  try {
    const n = Number.parseInt(localStorage.getItem('bbz.commsWidth') ?? '', 10);
    return Number.isFinite(n) && n >= COMMS_MIN && n <= COMMS_MAX ? n : 360;
  } catch {
    return 360;
  }
}
