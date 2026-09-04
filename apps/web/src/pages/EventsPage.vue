<script setup lang="ts">
/**
 * Ereignisübersicht (MASTER_PROMPT §13.6, V10 mockup): one chronological list
 * of **all** events — active and archived together, newest first, with an
 * "Archiv" column and a search box — beside the processing panel for the
 * selected event. Merges the former QueuePage + ArchivePage. Reactivation of an
 * archived event is the confirmation dialog inside `EventProcessingPanel`.
 */
import { computed, onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute } from 'vue-router';
import { eventsApi, PRIORITY_RANK, type EventListItem } from '@/lib/events';
import { useEventsStore } from '@/stores/events';
import PriorityBadge from '@/components/events/PriorityBadge.vue';
import PriorityPulse from '@/components/events/PriorityPulse.vue';
import EventProcessingPanel from '@/components/events/EventProcessingPanel.vue';

const { t, d } = useI18n();
const route = useRoute();
const events = useEventsStore();

const all = ref<EventListItem[]>([]);
const loading = ref(true);
const error = ref(false);
const search = ref('');
const onlyArchived = ref(route.query.archiv === '1');
const selectedId = ref<string | null>(
  typeof route.params.id === 'string' ? route.params.id : null,
);

const sorted = computed(() => {
  const q = search.value.trim().toLowerCase();
  return [...all.value]
    .filter((e) => !onlyArchived.value || e.status === 'archived')
    .filter((e) => !q || `${e.title}`.toLowerCase().includes(q) || e.status.includes(q))
    .sort((a, b) => {
      // newest first, but active events outrank archived at the same time
      const arch = Number(a.status === 'archived') - Number(b.status === 'archived');
      if (arch !== 0) return arch;
      const time = b.created_at.localeCompare(a.created_at);
      return time !== 0 ? time : PRIORITY_RANK[a.priority] - PRIORITY_RANK[b.priority];
    });
});

function select(id: string): void {
  selectedId.value = id;
  void events.loadDetail(id);
}

async function load(): Promise<void> {
  loading.value = true;
  error.value = false;
  try {
    all.value = (await eventsApi.list({ include_archived: 'true', limit: '200' })).items;
  } catch {
    error.value = true;
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  void load();
  void events.loadAlert();
});
watch(() => events.lastSeq, () => void load());
</script>

<template>
  <section class="events">
    <div class="view-head">
      <div>
        <div class="section-kicker">
          {{ t('events.kicker') }}
        </div>
        <h1>{{ t('events.title') }}</h1>
        <p>{{ t('events.subtitle') }}</p>
      </div>
    </div>

    <div class="detail-grid">
      <section class="card">
        <div class="card-head">
          <div>
            <div class="card-title">
              {{ t('events.listTitle') }}
            </div>
            <div class="card-subtitle">
              {{ t('events.listSubtitle') }}
            </div>
          </div>
          <label class="events__search">
            <span class="sr-only">{{ t('events.search') }}</span>
            <input
              v-model="search"
              class="input"
              type="search"
              :placeholder="t('events.search')"
            >
          </label>
        </div>
        <div class="card-body">
          <label class="events__filter">
            <input
              v-model="onlyArchived"
              type="checkbox"
            >
            {{ t('events.onlyArchived') }}
          </label>

          <p
            v-if="error"
            role="alert"
            class="events__error"
          >
            {{ t('events.loadError') }}
          </p>
          <p
            v-else-if="!loading && sorted.length === 0"
            class="muted"
          >
            {{ t('events.empty') }}
          </p>

          <div
            v-else
            class="events__table-wrap"
          >
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
                    {{ t('events.colEntry') }}
                  </th>
                  <th scope="col">
                    {{ t('queue.col.status') }}
                  </th>
                  <th scope="col">
                    {{ t('events.colArchive') }}
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="e in sorted"
                  :key="e.id"
                  class="events__row"
                  :class="{
                    'events__row--selected': e.id === selectedId,
                    'events__row--archived': e.status === 'archived',
                  }"
                  tabindex="0"
                  @click="select(e.id)"
                  @keydown.enter="select(e.id)"
                >
                  <td>
                    <span class="events__prio">
                      <PriorityPulse :priority="e.priority" />
                      <PriorityBadge :priority="e.priority" />
                    </span>
                  </td>
                  <td class="events__title">
                    {{ e.title }}
                  </td>
                  <td class="events__num">
                    {{ d(new Date(e.created_at), 'short') }}
                  </td>
                  <td>{{ t('event.status.' + e.status) }}</td>
                  <td>
                    <span
                      v-if="e.status === 'archived'"
                      class="tag gray"
                    >{{ t('events.archived') }}</span>
                    <span
                      v-else
                      class="muted"
                    >—</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section class="card">
        <div class="card-head">
          <div class="card-title">
            {{ t('events.detailTitle') }}
          </div>
        </div>
        <div class="card-body">
          <p
            v-if="!selectedId"
            class="muted"
          >
            {{ t('events.selectPrompt') }}
          </p>
          <EventProcessingPanel
            v-else
            :key="selectedId"
            :event-id="selectedId"
          />
        </div>
      </section>
    </div>
  </section>
</template>

<style scoped>
.events {
  display: grid;
  gap: 0.9rem;
  align-content: start;
}
.events__search {
  width: 16rem;
  max-width: 40vw;
}
.events__search input {
  width: 100%;
}
.events__filter {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.82rem;
  color: var(--bbz-text-muted);
  margin-bottom: 0.6rem;
}
.events__table-wrap {
  overflow: auto;
  max-height: 62vh;
}
.events__table-wrap th {
  position: sticky;
  top: 0;
  background: var(--bbz-surface);
  z-index: 1;
}
.events__row {
  cursor: pointer;
}
.events__row:hover {
  background: var(--bbz-surface-alt);
}
.events__row:focus-visible {
  outline: var(--bbz-focus-width) solid var(--bbz-focus-color);
  outline-offset: -2px;
}
.events__row--selected {
  background: var(--bbz-info-bg);
  box-shadow: inset 3px 0 0 var(--bbz-info);
}
/* archived rows read as "past" via muted text + a lighter title — not `opacity`,
   which drags every foreground/background pair below WCAG AA (#121) */
.events__row--archived {
  color: var(--bbz-text-muted);
}
.events__row--archived .events__title {
  font-weight: var(--bbz-weight-regular);
}
.events__prio {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
}
.events__title {
  font-weight: var(--bbz-weight-semibold);
}
.events__num {
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}
.events__error {
  color: var(--bbz-danger-text);
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}
</style>
