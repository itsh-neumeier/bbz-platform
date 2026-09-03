<script setup lang="ts">
/**
 * Arbeitsplatz (MASTER_PROMPT §13.3): the **Ereignisspeicher** — the shared
 * work queue as a table with the four always-visible lifecycle actions — over
 * the inline processing panel for the selected event. Critical / high rows
 * pulse (the global `prefers-reduced-motion` rule stills them).
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useEventsStore } from '@/stores/events';
import { useSessionStore } from '@/stores/session';
import { type EventListItem } from '@/lib/events';
import PriorityPulse from '@/components/events/PriorityPulse.vue';
import EventActions from '@/components/events/EventActions.vue';
import EventProcessingPanel from '@/components/events/EventProcessingPanel.vue';

const { t, d } = useI18n();
const events = useEventsStore();
const session = useSessionStore();

const selectedId = ref<string | null>(null);
const processingRef = ref<HTMLElement | null>(null);

const queue = computed(() => events.sortedQueue);
const openTotal = computed(() => queue.value.length);
const unhandled = computed(() => queue.value.filter((e) => e.status === 'new').length);
const mine = computed(
  () => queue.value.filter((e) => e.assignee_id && e.assignee_id === session.user?.id).length,
);

function ownerLabel(e: EventListItem): string {
  if (!e.assignee_id) return t('ownership.none');
  return e.assignee_id === session.user?.id ? t('ownership.you') : t('ownership.other');
}
function entryTime(e: EventListItem): string {
  return d(new Date(e.created_at), 'time');
}

function select(id: string): void {
  selectedId.value = id;
  void events.loadDetail(id);
  setTimeout(() => {
    processingRef.value?.scrollIntoView?.({ behavior: 'smooth', block: 'start' });
  }, 30);
}

async function load(): Promise<void> {
  await events.loadQueue();
  await events.loadAlert();
}

let poll: ReturnType<typeof setInterval> | undefined;
onMounted(() => {
  void load();
  poll = setInterval(() => void load(), 15_000);
});
onBeforeUnmount(() => clearInterval(poll));
// the shell's SSE stream advances lastSeq — refresh, and drop a vanished selection
watch(
  () => events.lastSeq,
  () => {
    void events.loadQueue();
    if (selectedId.value && !queue.value.some((e) => e.id === selectedId.value)) {
      // keep it — an archived event still has a detail; the panel shows it read-only
    }
  },
);
</script>

<template>
  <section class="wp">
    <section
      class="card wp__store"
      aria-labelledby="wp-store-h"
    >
      <div class="card-head wp__store-head">
        <div>
          <div class="section-kicker">
            {{ t('wp.store.kicker') }}
          </div>
          <div class="wp__store-titleline">
            <span
              id="wp-store-h"
              class="card-title"
            >{{ t('wp.store.title') }}</span>
            <span class="tag blue">3-S-Zentrale</span>
          </div>
          <div class="card-subtitle">
            {{ t('wp.store.subtitle') }}
          </div>
        </div>
        <div
          class="wp__counters"
          :aria-label="t('wp.store.title')"
        >
          <div class="wp__counter">
            <span>{{ t('wp.store.open') }}</span><strong>{{ openTotal }}</strong>
          </div>
          <div class="wp__counter">
            <span>{{ t('wp.store.new') }}</span><strong>{{ unhandled }}</strong>
          </div>
          <div class="wp__counter">
            <span>{{ t('wp.store.mine') }}</span><strong>{{ mine }}</strong>
          </div>
        </div>
      </div>

      <div class="wp__table-wrap">
        <table class="table">
          <thead>
            <tr>
              <th scope="col">
                {{ t('queue.col.priority') }}
              </th>
              <th scope="col">
                {{ t('queue.col.title') }}
              </th>
              <th scope="col">
                {{ t('wp.store.colStation') }}
              </th>
              <th scope="col">
                {{ t('wp.store.colEntry') }}
              </th>
              <th scope="col">
                {{ t('queue.col.status') }}
              </th>
              <th scope="col">
                {{ t('wp.store.colResponsible') }}
              </th>
              <th
                scope="col"
                class="wp__col-action"
              >
                {{ t('wp.store.colAction') }}
              </th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="e in queue"
              :key="e.id"
              class="wp__row"
              :class="{
                'wp__row--selected': e.id === selectedId,
                'wp__row--critical': e.priority === 'critical',
                'wp__row--high': e.priority === 'high',
              }"
              tabindex="0"
              @click="select(e.id)"
              @keydown.enter="select(e.id)"
            >
              <td>
                <span class="wp__prio">
                  <PriorityPulse :priority="e.priority" />
                  {{ t('event.priority.' + e.priority) }}
                </span>
              </td>
              <td class="wp__title">
                {{ e.title }}
              </td>
              <td class="muted">
                —
              </td>
              <td class="wp__num">
                {{ entryTime(e) }}
              </td>
              <td>{{ t('event.status.' + e.status) }}</td>
              <td :class="e.assignee_id === session.user?.id ? 'wp__owner-me' : 'muted'">
                {{ ownerLabel(e) }}
              </td>
              <td @click.stop>
                <EventActions
                  :event="e"
                  all
                />
              </td>
            </tr>
            <tr v-if="queue.length === 0">
              <td
                colspan="7"
                class="wp__empty"
              >
                {{ t('wp.store.empty') }}
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section
      ref="processingRef"
      class="card wp__processing"
    >
      <div
        v-if="!selectedId"
        class="wp__processing-empty"
      >
        <span
          class="wp__processing-icon"
          aria-hidden="true"
        >☑</span>
        <p>{{ t('wp.store.selectPrompt') }}</p>
      </div>
      <div
        v-else
        class="wp__processing-body"
      >
        <EventProcessingPanel
          :key="selectedId"
          :event-id="selectedId"
        />
      </div>
    </section>
  </section>
</template>

<style scoped>
.wp {
  display: grid;
  gap: 0.9rem;
  align-content: start;
}
.wp__store {
  overflow: hidden;
}
.wp__store-head {
  align-items: flex-start;
  flex-wrap: wrap;
}
.wp__store-titleline {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  margin: 2px 0;
}
.wp__counters {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}
.wp__counter {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  border: var(--bbz-border-width) solid var(--bbz-border);
  border-radius: var(--bbz-radius);
  background: var(--bbz-surface-alt);
  padding: 0.4rem 0.6rem;
  font-size: 0.78rem;
  color: var(--bbz-text-muted);
}
.wp__counter strong {
  color: var(--bbz-text);
  font-size: 1rem;
  font-variant-numeric: tabular-nums;
}
.wp__table-wrap {
  overflow: auto;
  max-height: 22rem;
}
.wp__table-wrap th {
  position: sticky;
  top: 0;
  background: var(--bbz-surface);
  z-index: 1;
}
.wp__col-action {
  text-align: right;
}
.wp__row td:last-child {
  min-width: 19rem;
}
.wp__table-wrap td {
  vertical-align: middle;
}
.wp__row {
  cursor: pointer;
}
.wp__row:hover {
  background: var(--bbz-surface-alt);
}
.wp__row:focus-visible {
  outline: var(--bbz-focus-width) solid var(--bbz-focus-color);
  outline-offset: -2px;
}
.wp__row--selected {
  background: var(--bbz-info-bg);
  box-shadow: inset 3px 0 0 var(--bbz-info);
}
.wp__row--critical {
  animation: wp-critical 1.5s ease-in-out infinite;
}
.wp__row--high {
  animation: wp-high 2.1s ease-in-out infinite;
}
@keyframes wp-critical {
  0%,
  100% {
    box-shadow: inset 4px 0 0 var(--bbz-prio-critical);
  }
  50% {
    box-shadow:
      inset 4px 0 0 var(--bbz-prio-critical),
      0 0 16px color-mix(in srgb, var(--bbz-prio-critical) 25%, transparent);
  }
}
@keyframes wp-high {
  0%,
  100% {
    box-shadow: inset 3px 0 0 var(--bbz-prio-high);
  }
  50% {
    box-shadow: inset 6px 0 0 var(--bbz-prio-high);
  }
}
.wp__row--selected.wp__row--critical,
.wp__row--selected.wp__row--high {
  animation: none;
  box-shadow: inset 3px 0 0 var(--bbz-info);
}
.wp__prio {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  white-space: nowrap;
}
.wp__title {
  font-weight: var(--bbz-weight-semibold);
}
.wp__num {
  font-variant-numeric: tabular-nums;
}
.wp__owner-me {
  color: var(--bbz-success-text);
  font-weight: var(--bbz-weight-semibold);
}
.wp__row td:last-child {
  text-align: right;
}
.wp__empty {
  text-align: center;
  padding: 1.5rem;
  color: var(--bbz-text-muted);
}
.wp__processing {
  min-height: 14rem;
}
.wp__processing-empty {
  min-height: 14rem;
  display: grid;
  place-content: center;
  justify-items: center;
  gap: 0.5rem;
  text-align: center;
  padding: 2rem;
  color: var(--bbz-text-muted);
}
.wp__processing-icon {
  width: 3rem;
  height: 3rem;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: var(--bbz-surface-alt);
  border: var(--bbz-border-width) solid var(--bbz-border);
  font-size: 1.4rem;
  color: var(--bbz-info);
}
.wp__processing-body {
  padding: var(--bbz-space-md);
}
</style>
