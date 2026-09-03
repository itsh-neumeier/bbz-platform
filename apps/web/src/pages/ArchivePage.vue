<script setup lang="ts">
/**
 * Archive view (E07-11 / #113) — every archived event, chronological, with the
 * full history and post-processing notes on the detail. Reactivation is the
 * dialog (#115). Nothing is ever deleted (MASTER_PROMPT §13.6 / ADR-0011).
 */
import { onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRouter } from 'vue-router';
import { eventsApi, type EventListItem } from '@/lib/events';
import PriorityBadge from '@/components/events/PriorityBadge.vue';

const { t, d } = useI18n();
const router = useRouter();

const items = ref<EventListItem[]>([]);
const loading = ref(true);
const error = ref(false);

onMounted(async () => {
  try {
    items.value = (await eventsApi.archivedList()).items;
  } catch {
    error.value = true;
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <section class="arch">
    <h1>{{ t('nav.archive') }}</h1>

    <p
      v-if="error"
      role="alert"
      class="arch__error"
    >
      {{ t('archive.loadError') }}
    </p>
    <p
      v-else-if="!loading && items.length === 0"
      class="arch__empty"
    >
      {{ t('archive.empty') }}
    </p>

    <table
      v-else
      class="arch__table"
    >
      <thead>
        <tr>
          <th scope="col">
            {{ t('queue.col.priority') }}
          </th>
          <th scope="col">
            {{ t('queue.col.title') }}
          </th>
          <th scope="col">
            {{ t('archive.archivedAt') }}
          </th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="e in items"
          :key="e.id"
          class="arch__row"
          tabindex="0"
          @click="router.push('/archiv/' + e.id)"
          @keydown.enter="router.push('/archiv/' + e.id)"
        >
          <td><PriorityBadge :priority="e.priority" /></td>
          <td class="arch__title">
            {{ e.title }}
          </td>
          <td>
            <time :datetime="e.updated_at">{{ d(new Date(e.updated_at), 'short') }}</time>
          </td>
        </tr>
      </tbody>
    </table>
  </section>
</template>

<style scoped>
.arch h1 {
  margin: 0 0 0.75rem;
  font-size: 1.25rem;
}
.arch__table {
  width: 100%;
  border-collapse: collapse;
}
.arch__table th,
.arch__table td {
  text-align: left;
  padding: 0.5rem 0.6rem;
  border-bottom: 1px solid var(--bbz-border);
}
.arch__table th {
  font-size: 0.75rem;
  color: var(--bbz-text-muted);
  text-transform: uppercase;
}
.arch__row {
  cursor: pointer;
}
.arch__row:hover {
  background: var(--bbz-surface-alt);
}
.arch__row:focus-visible {
  outline: 2px solid var(--bbz-accent);
  outline-offset: -2px;
}
.arch__title {
  font-weight: 600;
}
.arch__empty,
.arch__error {
  color: var(--bbz-text-muted);
}
.arch__error {
  color: var(--bbz-danger-text);
}
</style>
