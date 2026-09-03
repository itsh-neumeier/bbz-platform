import { onUnmounted, ref, shallowRef } from 'vue';
import { eventsApi } from '@/lib/events';

/**
 * SSE client for `/api/v1/events/stream` (E07-05 / #101).
 *
 * Catch-up is authoritative (ADR-0011 / docs/client-catchup): we connect with
 * `after_seq` = the last sequence we hold, replay the backlog, get a
 * `caught_up` marker, then follow live. On drop we reconnect with the same
 * `after_seq`; a later `event_seq` jump is a failover gap, not a loss. The
 * `status` ref drives the topbar sync indicator.
 */
export type SyncState = 'connecting' | 'catching-up' | 'connected' | 'reconnecting' | 'offline';

export interface DomainEventFrame {
  seq: number;
  type: string;
  data: Record<string, unknown>;
}

export function useEventStream(onFrame?: (f: DomainEventFrame) => void) {
  const status = ref<SyncState>('connecting');
  const lastSeq = ref(0);
  const source = shallowRef<EventSource | null>(null);
  let retry = 0;
  let retryTimer: number | undefined;
  let stopped = false;

  async function connect(): Promise<void> {
    if (stopped) return;
    if (typeof EventSource === 'undefined') {
      // no SSE in this runtime (SSR / jsdom tests) — stay quiet
      status.value = 'offline';
      return;
    }
    try {
      if (lastSeq.value === 0) {
        lastSeq.value = (await eventsApi.streamHead()).last_seq ?? 0;
      }
    } catch {
      /* head is a hint; 0 just means a full replay */
    }

    status.value = retry === 0 ? 'connecting' : 'reconnecting';
    const es = new EventSource(`/api/v1/events/stream?after_seq=${lastSeq.value}`, {
      withCredentials: true,
    });
    source.value = es;

    es.onopen = () => {
      status.value = 'catching-up';
    };

    es.addEventListener('caught_up', () => {
      retry = 0;
      status.value = 'connected';
    });

    es.onmessage = (ev) => handleFrame(ev);
    // named domain events arrive as `event: EVENT_TYPE` — a catch-all listener
    // is not possible, so the server also mirrors them onto the default channel
    // when a client asks; until then, re-dispatch known types.
    for (const type of KNOWN_EVENT_TYPES) es.addEventListener(type, (ev) => handleFrame(ev as MessageEvent));

    es.onerror = () => {
      es.close();
      source.value = null;
      if (stopped) return;
      status.value = navigator.onLine === false ? 'offline' : 'reconnecting';
      retry += 1;
      const wait = Math.min(30_000, 1000 * 2 ** Math.min(retry, 5));
      retryTimer = window.setTimeout(connect, wait);
    };
  }

  function handleFrame(ev: MessageEvent): void {
    const seq = Number(ev.lastEventId) || 0;
    if (seq) lastSeq.value = Math.max(lastSeq.value, seq);
    let data: Record<string, unknown> = {};
    try {
      data = ev.data ? JSON.parse(ev.data) : {};
    } catch {
      /* heartbeat / comment lines never reach here */
    }
    onFrame?.({ seq, type: ev.type === 'message' ? String(data.event_type ?? '') : ev.type, data });
  }

  function stop(): void {
    stopped = true;
    window.clearTimeout(retryTimer);
    source.value?.close();
    source.value = null;
  }

  connect();
  onUnmounted(stop);

  return { status, lastSeq, stop };
}

const KNOWN_EVENT_TYPES = [
  'EVENT_CREATED',
  'EVENT_ACCEPTED',
  'EVENT_ACKNOWLEDGED',
  'EVENT_OPENED',
  'EVENT_ARCHIVED',
  'EVENT_REACTIVATED',
  'EVENT_UPDATED',
  'EVENT_ASSIGNED',
  'EVENT_TAKEN_OVER',
  'EVENT_NOTE_ADDED',
  'CLIENT_POPUP_RAISED',
];
