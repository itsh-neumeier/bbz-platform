import { defineStore } from 'pinia';
import {
  eventsApi,
  PRIORITY_RANK,
  type EventDetail,
  type EventListItem,
  type EventPriority,
  type PriorityAlert,
} from '@/lib/events';
import { ConflictError } from '@/lib/apiClient';
import type { SyncState } from '@/composables/useEventStream';

interface State {
  queue: EventListItem[];
  detail: Record<string, EventDetail>;
  alert: PriorityAlert;
  loading: boolean;
  error: string | null;
  syncState: SyncState;
  lastSeq: number;
}

/** Work-queue order: priority rank, then oldest first (MASTER_PROMPT §13.6). */
function queueSort(a: EventListItem, b: EventListItem): number {
  const p = PRIORITY_RANK[a.priority] - PRIORITY_RANK[b.priority];
  return p !== 0 ? p : a.created_at.localeCompare(b.created_at);
}

export const useEventsStore = defineStore('events', {
  state: (): State => ({
    queue: [],
    detail: {},
    alert: { active: false, events: [] },
    loading: false,
    error: null,
    syncState: 'connecting',
    lastSeq: 0,
  }),
  getters: {
    sortedQueue: (s): EventListItem[] => [...s.queue].sort(queueSort),
    topPriority: (s): EventPriority | null =>
      s.alert.events.length ? s.alert.events[0].priority : null,
  },
  actions: {
    async loadQueue(): Promise<void> {
      this.loading = true;
      this.error = null;
      try {
        this.queue = (await eventsApi.workQueue()).items;
      } catch (e) {
        this.error = e instanceof Error ? e.message : String(e);
      } finally {
        this.loading = false;
      }
    },

    async loadAlert(): Promise<void> {
      try {
        this.alert = await eventsApi.priorityAlert();
      } catch {
        /* the banner just stays hidden */
      }
    },

    async loadDetail(id: string): Promise<EventDetail> {
      const d = await eventsApi.get(id);
      this.detail[id] = d;
      this.mergeIntoQueue(d);
      return d;
    },

    /** Run the single lifecycle action for an event's current status. */
    async transition(
      id: string,
      action: 'accept' | 'acknowledge' | 'open' | 'archive',
    ): Promise<void> {
      const current = this.detail[id] ?? this.queue.find((e) => e.id === id);
      if (!current) throw new Error('unknown event');
      let newStatus: string;
      try {
        // the response is the minimal EventOut — take the new status + version,
        // then re-hydrate the full detail if it is on screen.
        const out = await eventsApi.transition(id, action, current.version);
        newStatus = out.status;
        const q = this.queue.findIndex((e) => e.id === id);
        if (q >= 0) this.queue[q] = { ...this.queue[q], status: out.status, version: out.version };
      } catch (e) {
        if (e instanceof ConflictError) {
          await this.loadDetail(id).catch(() => undefined);
          await this.loadQueue().catch(() => undefined);
        }
        throw e;
      }
      if (newStatus === 'archived') this.queue = this.queue.filter((e) => e.id !== id);
      if (this.detail[id]) await this.loadDetail(id).catch(() => undefined);
      await this.loadAlert();
    },

    async addNote(id: string, body: string): Promise<void> {
      await eventsApi.addNote(id, body);
      await this.loadDetail(id);
    },

    setSync(state: SyncState, seq: number): void {
      this.syncState = state;
      this.lastSeq = seq;
    },

    /** Nudge from the SSE stream — a domain event touched something. */
    onStreamFrame(type: string, aggregateId: string | undefined): void {
      if (!type.startsWith('EVENT_') && type !== 'CLIENT_POPUP_RAISED') return;
      // cheap + correct: re-pull the small work queue + the alert
      void this.loadQueue();
      void this.loadAlert();
      if (aggregateId && this.detail[aggregateId]) void this.loadDetail(aggregateId);
    },

    mergeIntoQueue(d: EventDetail): void {
      const item: EventListItem = {
        id: d.id,
        title: d.title,
        priority: d.priority,
        status: d.status,
        bbz_id: d.bbz_id,
        workplace_id: d.workplace_id,
        version: d.version,
        assignee_id: d.assignee_id,
        created_at: d.created_at,
        updated_at: d.updated_at,
      };
      const i = this.queue.findIndex((e) => e.id === d.id);
      if (d.status === 'archived') {
        if (i >= 0) this.queue.splice(i, 1);
      } else if (i >= 0) {
        this.queue[i] = item;
      } else {
        this.queue.push(item);
      }
    },
  },
});
