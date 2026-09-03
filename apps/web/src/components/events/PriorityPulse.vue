<script setup lang="ts">
/**
 * A pulsing marker for an unhandled critical/high event (E07-07 / #105).
 * The animation is suppressed under `prefers-reduced-motion` — a solid dot
 * remains so the signal is not lost, only the motion.
 */
import { computed } from 'vue';
import { useReducedMotion } from '@/composables/useReducedMotion';
import type { EventPriority } from '@/lib/events';

const props = defineProps<{ priority: EventPriority }>();
const { reduced } = useReducedMotion();

const active = computed(() => props.priority === 'critical' || props.priority === 'high');
</script>

<template>
  <span
    v-if="active"
    :class="['pulse', 'pulse--' + priority, { 'pulse--still': reduced }]"
    aria-hidden="true"
  />
</template>

<style scoped>
.pulse {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex: none;
}
.pulse--critical {
  background: var(--bbz-prio-critical);
}
.pulse--high {
  background: var(--bbz-prio-high);
}
.pulse:not(.pulse--still) {
  animation: bbz-pulse 1.4s ease-out infinite;
}
@keyframes bbz-pulse {
  0% {
    box-shadow: 0 0 0 0 currentColor;
    opacity: 1;
  }
  70% {
    box-shadow: 0 0 0 8px transparent;
    opacity: 0.85;
  }
  100% {
    box-shadow: 0 0 0 0 transparent;
    opacity: 1;
  }
}
.pulse--critical {
  color: var(--bbz-prio-critical);
}
.pulse--high {
  color: var(--bbz-prio-high);
}
</style>
