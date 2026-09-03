<script setup lang="ts">
/**
 * Work queue (E07-06 / #103) — the active event queue ordered by priority rank
 * then age, with the one lifecycle action per row. Live via the SSE stream.
 */
import { onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRouter } from 'vue-router';
import { useEventsStore } from '@/stores/events';
import PriorityBadge from '@/components/events/PriorityBadge.vue';
import PriorityPulse from '@/components/events/PriorityPulse.vue';
import EventActions from '@/components/events/EventActions.vue';

const { t } = useI18n();
const router = useRouter();
const events = useEventsStore();

onMounted(() => {
  events.loadQueue();
  events.loadAlert();
});
</script>

<template>
  <section class="queue">
    <header class="queue__head">
      <h1>{{ t('nav.events') }}</h1>
      <span class="queue__meta">{{ t('queue.count', events.sortedQueue.length) }}</span>
    </header>

    <p
      v-if="events.error"
      class="queue__error"
      role="alert"
    >
      {{ t('queue.loadError') }}
    </p>

    <p
      v-else-if="!events.loading && events.sortedQueue.length === 0"
      class="queue__empty"
    >
      {{ t('queue.empty') }}
    </p>

    <table
      v-else
      class="queue__table"
    >
      <thead>
        <tr>
          <th scope="col" />
          <th scope="col">
            {{ t('queue.col.priority') }}
          </th>
          <th scope="col">
            {{ t('queue.col.title') }}
          </th>
          <th scope="col">
            {{ t('queue.col.status') }}
          </th>
          <th scope="col">
            {{ t('queue.col.actions') }}
          </th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="e in events.sortedQueue"
          :key="e.id"
          class="queue__row"
          tabindex="0"
          @click="router.push('/ereignisse/' + e.id)"
          @keydown.enter="router.push('/ereignisse/' + e.id)"
        >
          <td><PriorityPulse :priority="e.priority" /></td>
          <td><PriorityBadge :priority="e.priority" /></td>
          <td class="queue__title">
            {{ e.title }}
          </td>
          <td>{{ t('event.status.' + e.status) }}</td>
          <td @click.stop>
            <EventActions
              :event="e"
              show-open
            />
          </td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<style scoped>
.queue__head {
  display: flex;
  align-items: baseline;
  gap: 0.75rem;
}
.queue__head h1 {
  margin: 0;
  font-size: 1.25rem;
}
.queue__meta {
  color: var(--bbz-text-muted);
  font-size: 0.85rem;
}
.queue__table {
  width: 100%;
  border-collapse: collapse;
  margin-top: 0.75rem;
}
.queue__table th,
.queue__table td {
  text-align: left;
  padding: 0.5rem 0.6rem;
  border-bottom: 1px solid var(--bbz-border);
  vertical-align: middle;
}
.queue__table th {
  font-size: 0.75rem;
  color: var(--bbz-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.02em;
}
.queue__row {
  cursor: pointer;
}
.queue__row:hover {
  background: var(--bbz-surface-alt);
}
.queue__row:focus-visible {
  outline: var(--bbz-focus-width) solid var(--bbz-focus-color);
  outline-offset: -2px;
}
.queue__title {
  font-weight: 600;
}
.queue__empty,
.queue__error {
  margin-top: 1rem;
  color: var(--bbz-text-muted);
}
.queue__error {
  color: var(--bbz-danger-text);
}
.queue__foot {
  margin-top: 0.75rem;
  font-size: 0.8rem;
}
.queue__sync--connected {
  color: var(--bbz-success-text);
}
.queue__sync--offline {
  color: var(--bbz-danger-text);
}
</style>
