import { defineStore } from 'pinia';
import { getMeta, type Meta } from '@/api/client';

// Placeholder for the real session/auth store (Phase 1: providers local /
// entra_oidc / ldap_ad). Today it only tracks backend meta and a persisted
// comms-sidebar width (the mockup requires the sidebar width to persist).
export const useSessionStore = defineStore('session', {
  state: () => ({
    meta: null as Meta | null,
    commsWidth: readPersistedWidth(),
    loading: false,
  }),
  actions: {
    async loadMeta() {
      this.loading = true;
      try {
        this.meta = await getMeta();
      } finally {
        this.loading = false;
      }
    },
    setCommsWidth(px: number) {
      this.commsWidth = px;
      try {
        localStorage.setItem('bbz.commsWidth', String(px));
      } catch {
        /* private mode / storage disabled — non-fatal */
      }
    },
  },
});

function readPersistedWidth(): number {
  try {
    const raw = localStorage.getItem('bbz.commsWidth');
    const n = raw ? Number.parseInt(raw, 10) : Number.NaN;
    return Number.isFinite(n) && n >= 280 && n <= 640 ? n : 360;
  } catch {
    return 360;
  }
}
