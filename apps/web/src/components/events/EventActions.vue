<script setup lang="ts">
/**
 * The single lifecycle button for an event, driven by its status
 * (new→accept→acknowledge→open→archive). "Bearbeiten" opens the detail.
 */
import { ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRouter } from 'vue-router';
import { ConflictError } from '@/lib/apiClient';
import { NEXT_ACTION, type EventListItem } from '@/lib/events';
import { useEventsStore } from '@/stores/events';
import { useSessionStore } from '@/stores/session';

const props = defineProps<{ event: EventListItem; showOpen?: boolean }>();
const { t } = useI18n();
const router = useRouter();
const events = useEventsStore();
const session = useSessionStore();

const busy = ref(false);
const conflict = ref(false);

const PERM: Record<string, string> = {
  accept: 'events.accept',
  acknowledge: 'events.acknowledge',
  open: 'events.open',
  archive: 'events.archive',
};

async function run(): Promise<void> {
  const action = NEXT_ACTION[props.event.status];
  if (!action) return;
  busy.value = true;
  conflict.value = false;
  try {
    await events.transition(props.event.id, action);
  } catch (e) {
    if (e instanceof ConflictError) conflict.value = true;
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <div class="acts">
    <button
      v-if="NEXT_ACTION[event.status] && session.can(PERM[NEXT_ACTION[event.status]!])"
      type="button"
      class="acts__primary"
      :disabled="busy"
      @click="run"
    >
      {{ t('event.action.' + NEXT_ACTION[event.status]) }}
    </button>
    <button
      v-if="showOpen"
      type="button"
      class="acts__secondary"
      @click="router.push('/ereignisse/' + event.id)"
    >
      {{ t('event.action.edit') }}
    </button>
    <span
      v-if="conflict"
      class="acts__conflict"
      role="alert"
    >{{ t('event.conflict') }}</span>
  </div>
</template>

<style scoped>
.acts {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}
.acts__primary,
.acts__secondary {
  padding: 0.3rem 0.7rem;
  border-radius: var(--bbz-radius);
  font-size: 0.85rem;
  cursor: pointer;
  border: 1px solid var(--bbz-border);
}
.acts__primary {
  background: var(--bbz-accent);
  color: #fff;
  border-color: transparent;
}
.acts__primary:disabled {
  opacity: 0.6;
  cursor: progress;
}
.acts__secondary {
  background: var(--bbz-bg);
  color: var(--bbz-text);
}
.acts__primary:focus-visible,
.acts__secondary:focus-visible {
  outline: var(--bbz-focus-width) solid var(--bbz-focus-color);
  outline-offset: 2px;
}
.acts__conflict {
  font-size: 0.8rem;
  color: var(--bbz-warn-text);
}
</style>
