<script setup lang="ts">
/**
 * Contact call-priority badge (E14-08 / #299). §13.9: niedrig=blau,
 * mittel=orange, hoch=rot — but the level must be readable *without* colour
 * perception too (the AC), so this is a text badge, not a bare colour dot.
 * Same shape as PriorityBadge.vue (events); one component so every place a
 * contact priority shows (phone book, quick-dial overlay, comms mini-search)
 * looks and reads identically.
 */
import { useI18n } from 'vue-i18n';
import type { ContactPriority } from '@/lib/contacts';

defineProps<{ priority: ContactPriority }>();
const { t } = useI18n();
</script>

<template>
  <span
    class="cpb"
    :class="'cpb--' + priority"
  >{{ t('contact.priority.' + priority) }}</span>
</template>

<style scoped>
.cpb {
  display: inline-block;
  padding: 0.1rem 0.45rem;
  border-radius: var(--bbz-radius-sm);
  font-size: 0.72rem;
  font-weight: 600;
  white-space: nowrap;
  line-height: 1.4;
}
.cpb--low {
  background: var(--bbz-prio-low);
  color: var(--bbz-on-prio-low);
}
.cpb--medium {
  background: var(--bbz-prio-medium);
  color: var(--bbz-on-prio-medium);
}
.cpb--high {
  background: var(--bbz-prio-high);
  color: var(--bbz-on-prio-high);
}
</style>
