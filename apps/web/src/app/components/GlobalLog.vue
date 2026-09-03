<script setup lang="ts">
/**
 * "Ereignisse · Logbuch" — the cross-workplace activity feed in the right
 * column (MASTER_PROMPT §13.1, V10 mockup `.global-log`). Read-only view over
 * the append-only domain-event log (`GET /events/logbook`). Refreshes on a
 * poll and whenever the shell's SSE stream advances.
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRouter } from 'vue-router';
import { eventsApi, type LogbookEntry } from '@/lib/events';
import { useEventsStore } from '@/stores/events';

const { t, d } = useI18n();
const router = useRouter();
const events = useEventsStore();

const entries = ref<LogbookEntry[]>([]);
const failed = ref(false);

async function load(): Promise<void> {
  try {
    entries.value = (await eventsApi.logbook(30)).items;
    failed.value = false;
  } catch {
    failed.value = true;
  }
}

const time = (iso: string): string => d(new Date(iso), 'time');
const typeLabel = (k: string): string => t('logbook.type.' + k, k.replace(/^EVENT_/, ''));

const grouped = computed(() => entries.value);

let poll: ReturnType<typeof setInterval> | undefined;
onMounted(() => {
  void load();
  poll = setInterval(() => void load(), 20_000);
});
onBeforeUnmount(() => clearInterval(poll));
// the shell's SSE stream advances lastSeq on any domain event — refresh then
watch(
  () => events.lastSeq,
  () => void load(),
);
</script>

<template>
  <section
    class="glog"
    aria-labelledby="glog-h"
  >
    <div class="glog__head">
      <div>
        <b id="glog-h">{{ t('logbook.title') }}</b>
        <small>{{ t('logbook.subtitle') }}</small>
      </div>
    </div>

    <ul class="glog__list">
      <li
        v-for="e in grouped"
        :key="e.event_seq"
        class="glog__entry"
        :class="'glog__entry--' + e.priority"
      >
        <button
          type="button"
          class="glog__row"
          @click="router.push('/ereignisse/' + e.event_id)"
        >
          <time :datetime="e.occurred_at_utc">{{ time(e.occurred_at_utc) }}</time>
          <span class="glog__body">
            <b>{{ e.title }}</b>
            <span class="glog__meta">
              <span class="glog__type">{{ typeLabel(e.event_type) }}</span>
              <span
                v-if="e.actor"
                class="glog__actor"
              >· {{ e.actor }}</span>
            </span>
          </span>
        </button>
      </li>
      <li
        v-if="entries.length === 0"
        class="glog__empty"
      >
        {{ failed ? t('logbook.failed') : t('logbook.empty') }}
      </li>
    </ul>
  </section>
</template>

<style scoped>
.glog {
  display: flex;
  flex-direction: column;
  min-height: 0;
  background: var(--bbz-bg);
}
.glog__head {
  min-height: 3rem;
  padding: 0.6rem 0.8rem;
  border-bottom: var(--bbz-border-width) solid var(--bbz-border);
  display: flex;
  align-items: center;
  background: var(--bbz-surface);
}
.glog__head b {
  display: block;
  font-family: var(--bbz-font-head);
  font-size: 0.85rem;
}
.glog__head small {
  display: block;
  color: var(--bbz-text-muted);
  font-size: 0.68rem;
  margin-top: 2px;
}
.glog__list {
  list-style: none;
  margin: 0;
  padding: 0.5rem;
  overflow: auto;
  display: grid;
  gap: 0.35rem;
}
.glog__row {
  width: 100%;
  display: grid;
  grid-template-columns: 3.4rem 1fr;
  gap: 0.5rem;
  text-align: left;
  padding: 0.5rem 0.55rem;
  border: var(--bbz-border-width) solid var(--bbz-border);
  border-left: 3px solid var(--bbz-border-strong);
  border-radius: var(--bbz-radius-sm);
  background: var(--bbz-surface);
  color: var(--bbz-text);
  min-height: 0;
}
.glog__row:hover {
  background: var(--bbz-surface-alt);
}
.glog__entry--critical .glog__row {
  border-left-color: var(--bbz-prio-critical);
}
.glog__entry--high .glog__row {
  border-left-color: var(--bbz-prio-high);
}
.glog__entry--medium .glog__row {
  border-left-color: var(--bbz-prio-medium);
}
.glog__entry--low .glog__row {
  border-left-color: var(--bbz-prio-low);
}
.glog__row time {
  font-size: 0.68rem;
  color: var(--bbz-text-subtle);
  font-variant-numeric: tabular-nums;
  padding-top: 1px;
}
.glog__body b {
  display: block;
  font-size: 0.78rem;
  font-weight: var(--bbz-weight-semibold);
  line-height: var(--bbz-leading-tight);
}
.glog__meta {
  display: block;
  color: var(--bbz-text-muted);
  font-size: 0.68rem;
  margin-top: 2px;
}
.glog__type {
  font-weight: var(--bbz-weight-medium);
  color: var(--bbz-text);
}
.glog__empty {
  color: var(--bbz-text-muted);
  font-size: 0.78rem;
  padding: 0.75rem 0.55rem;
}
</style>
