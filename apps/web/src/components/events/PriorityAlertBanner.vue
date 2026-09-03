<script setup lang="ts">
/**
 * Global topbar banner for unaccepted high/critical events (E07-13 / #117).
 * Shows on every page *except* the work queue (where the events are already the
 * whole view). Clicking jumps to the queue.
 */
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute, useRouter } from 'vue-router';
import { useEventsStore } from '@/stores/events';

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const events = useEventsStore();

const show = computed(
  () => events.alert.active && events.alert.events.length > 0 && route.name !== 'events',
);
const count = computed(() => events.alert.events.length);
const worst = computed(() => events.topPriority ?? 'high');
</script>

<template>
  <button
    v-if="show"
    type="button"
    :class="['alert-banner', 'alert-banner--' + worst]"
    @click="router.push('/ereignisse')"
  >
    <strong>{{ t('event.alertBanner', count) }}</strong>
    <span class="alert-banner__lead">{{ events.alert.events[0].title }}</span>
  </button>
</template>

<style scoped>
.alert-banner {
  display: flex;
  align-items: baseline;
  gap: 0.6rem;
  padding: 0.35rem 0.75rem;
  border: 0;
  border-radius: var(--bbz-radius);
  color: #fff;
  cursor: pointer;
  font-size: 0.9rem;
  max-width: 40vw;
}
.alert-banner--critical {
  background: var(--bbz-prio-critical);
}
.alert-banner--high {
  background: var(--bbz-prio-high);
}
.alert-banner__lead {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 0.82rem;
  opacity: 0.9;
}
.alert-banner:focus-visible {
  outline: 2px solid #fff;
  outline-offset: 2px;
}
</style>
