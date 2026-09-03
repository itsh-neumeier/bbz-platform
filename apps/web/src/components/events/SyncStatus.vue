<script setup lang="ts">
import { useI18n } from 'vue-i18n';
import type { SyncState } from '@/composables/useEventStream';

const props = defineProps<{ state: SyncState; seq: number }>();
const { t } = useI18n();

const label: Record<SyncState, string> = {
  connecting: 'sync.connecting',
  'catching-up': 'sync.connecting',
  connected: 'sync.connected',
  reconnecting: 'sync.reconnecting',
  offline: 'sync.offline',
};
</script>

<template>
  <span
    class="sync"
    :class="'sync--' + props.state"
    role="status"
    :title="props.seq ? t('sync.lastSeq', { seq: props.seq }) : ''"
  >
    <span
      class="sync__dot"
      aria-hidden="true"
    />
    {{ t(label[props.state]) }}
  </span>
</template>

<style scoped>
.sync {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.8rem;
  color: var(--bbz-text-muted);
}
.sync__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
}
.sync--connected {
  color: var(--bbz-success-text);
}
.sync--reconnecting,
.sync--connecting,
.sync--catching-up {
  color: var(--bbz-warn-text);
}
.sync--offline {
  color: var(--bbz-danger-text);
}
</style>
