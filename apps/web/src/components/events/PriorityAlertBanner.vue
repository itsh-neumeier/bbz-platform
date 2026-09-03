<script setup lang="ts">
/**
 * Global topbar alert for unaccepted high/critical events (E07-13 / #117,
 * MASTER_PROMPT §13.7): on every page *except* the Arbeitsplatz (where the
 * Ereignisspeicher is already the whole view). Sits before the clock; clicking
 * jumps to the queue and opens the event. Animated (V10 `.priority-top-alert`);
 * the global `prefers-reduced-motion` rule stills it.
 */
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute, useRouter } from 'vue-router';
import { useEventsStore } from '@/stores/events';

const { t } = useI18n();
const route = useRoute();
const router = useRouter();
const events = useEventsStore();

const HIDDEN_ON = new Set(['workplace', 'events']);
const show = computed(
  () =>
    events.alert.active &&
    events.alert.events.length > 0 &&
    !HIDDEN_ON.has(String(route.name)),
);
const count = computed(() => events.alert.events.length);
const worst = computed(() => events.topPriority ?? 'high');

function open(): void {
  const first = events.alert.events[0];
  void router.push(first ? `/ereignisse/${first.id}` : '/ereignisse');
}
</script>

<template>
  <button
    v-if="show"
    type="button"
    class="palert"
    :class="'palert--' + worst"
    :aria-label="t('event.alertBanner', count)"
    @click="open"
  >
    <span
      class="palert__icon"
      aria-hidden="true"
    >!</span>
    <span class="palert__copy">
      <b>{{ t('event.alertBanner', count) }}</b>
      <small>{{ events.alert.events[0].title }}</small>
    </span>
  </button>
</template>

<style scoped>
.palert {
  display: flex;
  align-items: center;
  gap: 0.55rem;
  min-width: 14rem;
  max-width: 19rem;
  padding: 0.4rem 0.7rem;
  border: var(--bbz-border-width) solid color-mix(in srgb, var(--bbz-prio-high) 55%, transparent);
  border-radius: var(--bbz-radius);
  color: #fff;
  cursor: pointer;
  text-align: left;
  animation: palert-pulse 1.5s ease-in-out infinite;
}
.palert--critical {
  background: var(--bbz-prio-critical);
  border-color: color-mix(in srgb, var(--bbz-prio-critical) 55%, transparent);
}
.palert--high {
  background: var(--bbz-prio-high);
}
.palert__icon {
  width: 1.7rem;
  height: 1.7rem;
  flex: none;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-family: var(--bbz-font-head);
  font-weight: var(--bbz-weight-bold);
  font-size: 1.1rem;
  background: rgb(255 255 255 / 18%);
}
.palert__copy {
  min-width: 0;
}
.palert__copy b {
  display: block;
  font-size: 0.78rem;
  line-height: var(--bbz-leading-tight);
}
.palert__copy small {
  display: block;
  font-size: 0.68rem;
  color: rgb(255 255 255 / 85%);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  margin-top: 2px;
}
.palert:focus-visible {
  outline: var(--bbz-focus-width) solid #fff;
  outline-offset: 2px;
}
@keyframes palert-pulse {
  0%,
  100% {
    box-shadow: 0 0 0 0 color-mix(in srgb, var(--bbz-prio-high) 40%, transparent);
  }
  50% {
    box-shadow: 0 0 0 5px color-mix(in srgb, var(--bbz-prio-high) 14%, transparent);
  }
}
@media (max-width: 1280px) {
  .palert {
    min-width: 0;
    max-width: 12rem;
  }
  .palert__copy small {
    display: none;
  }
}
</style>
