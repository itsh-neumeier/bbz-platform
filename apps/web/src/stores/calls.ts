import { defineStore } from 'pinia';
import {
  telephonyApi,
  PRIORITY_RANK,
  type Call,
  type CallCategory,
  type CallDocumentation,
  type Line,
} from '@/lib/telephony';

interface State {
  ringing: Call[];
  history: Call[];
  lines: Line[];
  /** the call the operator is currently on (connected / held / pending doc). */
  active: Call | null;
  doc: CallDocumentation | null;
  pendingDocCount: number;
  error: string | null;
  busy: boolean;
}

const LIVE_STATES = new Set(['connected', 'held', 'transferring', 'ended_pending_documentation']);

/** priority (high→low, unknown last), then longest wait first. */
function ringingSort(a: Call, b: Call): number {
  const pa = PRIORITY_RANK[a.caller_priority ?? 'unknown'];
  const pb = PRIORITY_RANK[b.caller_priority ?? 'unknown'];
  if (pa !== pb) return pa - pb;
  return (a.started_at ?? a.created_at).localeCompare(b.started_at ?? b.created_at);
}

export const useCallsStore = defineStore('calls', {
  state: (): State => ({
    ringing: [],
    history: [],
    lines: [],
    active: null,
    doc: null,
    pendingDocCount: 0,
    error: null,
    busy: false,
  }),
  getters: {
    sortedRinging: (s): Call[] => [...s.ringing].sort(ringingSort),
    /** documentation is mandatory before a call can be closed (E11-10). */
    docRequired: (s): boolean =>
      s.active?.state === 'ended_pending_documentation' ||
      (s.active !== null && !!s.doc && !s.doc.mandatory_done && LIVE_STATES.has(s.active.state)),
  },
  actions: {
    async refresh(): Promise<void> {
      try {
        // each endpoint is permission-gated independently — one 403 (e.g. no
        // `calls.view_history`) must not blank the rest of the panel.
        const [ringing, history, lines, pending] = await Promise.all([
          telephonyApi.ringing().catch(() => ({ items: [], next_cursor: null })),
          telephonyApi.history({ limit: 25 }).catch(() => ({ items: [], next_cursor: null })),
          telephonyApi.lines().catch(() => ({ lines: [] })),
          telephonyApi.pendingDocs().catch(() => ({ calls: [] })),
        ]);
        this.ringing = ringing.items;
        this.history = history.items;
        this.lines = lines.lines;
        this.pendingDocCount = pending.calls.length;
        const live = history.items.find((c) => LIVE_STATES.has(c.state));
        await this.setActive(live ?? null);
        this.error = null;
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e);
      }
    },

    async setActive(call: Call | null): Promise<void> {
      const sameCall = call !== null && this.active?.id === call.id;
      this.active = call;
      if (!call) {
        this.doc = null;
        return;
      }
      // only (re)load the documentation when the active call actually changes —
      // a periodic refresh must not clobber what the operator is typing.
      if (sameCall && this.doc?.call_id === call.id) return;
      try {
        this.doc = await telephonyApi.getDoc(call.id);
      } catch {
        this.doc = null;
      }
    },

    async control(
      action: 'answer' | 'hangup' | 'hold' | 'resume',
      id: string,
    ): Promise<void> {
      this.busy = true;
      this.error = null;
      try {
        const r = await telephonyApi[action](id);
        if (!r.accepted && r.detail) this.error = r.detail;
        await this.refresh();
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e);
      } finally {
        this.busy = false;
      }
    },

    async transfer(id: string, destination: string): Promise<void> {
      this.busy = true;
      try {
        const r = await telephonyApi.transfer(id, destination);
        if (!r.accepted && r.detail) this.error = r.detail;
        await this.refresh();
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e);
      } finally {
        this.busy = false;
      }
    },

    async dial(lineId: string, destination: string): Promise<void> {
      this.busy = true;
      this.error = null;
      try {
        const r = await telephonyApi.dial(lineId, destination);
        if (!r.accepted && r.detail) this.error = r.detail;
        await this.refresh();
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e);
      } finally {
        this.busy = false;
      }
    },

    async saveDoc(category: CallCategory | null, freeText: string): Promise<void> {
      if (!this.active) return;
      this.busy = true;
      try {
        this.doc = await telephonyApi.putDoc(this.active.id, {
          category,
          free_text: freeText.trim() || null,
        });
        await this.refresh();
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e);
      } finally {
        this.busy = false;
      }
    },

    /** SSE nudge — a CALL_/LINE_ frame means the telephony state moved. */
    onStreamFrame(type: string): void {
      if (type.startsWith('CALL_') || type.startsWith('LINE_')) void this.refresh();
    },
  },
});
