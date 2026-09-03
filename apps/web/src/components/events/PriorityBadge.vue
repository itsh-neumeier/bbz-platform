<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import type { EventPriority } from '@/lib/events';

defineProps<{ priority: EventPriority }>();
const { t } = useI18n();
</script>

<template>
  <span :class="['prio', 'prio--' + priority]">{{ t('event.priority.' + priority) }}</span>
</template>

<style scoped>
.prio {
  display: inline-block;
  padding: 0.1rem 0.5rem;
  border-radius: 3px;
  font-size: 0.75rem;
  font-weight: 600;
  color: #fff;
  white-space: nowrap;
}
.prio--critical {
  background: var(--bbz-prio-critical);
}
.prio--high {
  background: var(--bbz-prio-high);
}
.prio--medium {
  background: var(--bbz-prio-medium);
}
.prio--low {
  background: var(--bbz-prio-low);
}
</style>
