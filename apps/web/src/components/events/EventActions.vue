<script setup lang="ts">
/**
 * Event lifecycle actions (MASTER_PROMPT §13.3 — "Aktionen immer sichtbar":
 * Annehmen · Quittieren · Bearbeiten · Archivieren). With `all` (the
 * Ereignisspeicher / processing panel) every action is shown and disabled by
 * status; without it (compact contexts) only the single next action plus an
 * optional "Bearbeiten" link.
 */
import { ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRouter } from 'vue-router';
import { ConflictError } from '@/lib/apiClient';
import { NEXT_ACTION, type EventListItem, type EventStatus } from '@/lib/events';
import { useEventsStore } from '@/stores/events';
import { useSessionStore } from '@/stores/session';

const props = defineProps<{ event: EventListItem; showOpen?: boolean; all?: boolean }>();
const { t } = useI18n();
const router = useRouter();
const events = useEventsStore();
const session = useSessionStore();

const busy = ref('');
const conflict = ref(false);

type Verb = 'accept' | 'acknowledge' | 'open' | 'archive';
const PERM: Record<Verb, string> = {
  accept: 'events.accept',
  acknowledge: 'events.acknowledge',
  open: 'events.open',
  archive: 'events.archive',
};
/** the status a verb acts from — the button is enabled only in that status */
const FROM: Record<Verb, EventStatus> = {
  accept: 'new',
  acknowledge: 'accepted',
  open: 'acknowledged',
  archive: 'opened',
};
const ALL_VERBS: Verb[] = ['accept', 'acknowledge', 'open', 'archive'];

async function run(verb: Verb): Promise<void> {
  busy.value = verb;
  conflict.value = false;
  try {
    await events.transition(props.event.id, verb);
  } catch (e) {
    if (e instanceof ConflictError) conflict.value = true;
  } finally {
    busy.value = '';
  }
}
</script>

<template>
  <div
    class="acts"
    :class="{ 'acts--all': all }"
  >
    <template v-if="all">
      <button
        v-for="verb in ALL_VERBS"
        :key="verb"
        type="button"
        class="btn sm"
        :class="{ success: verb === 'accept', primary: verb === 'open', ghost: verb === 'archive' }"
        :disabled="
          busy !== '' || event.status !== FROM[verb] || !session.can(PERM[verb])
        "
        @click="run(verb)"
      >
        {{ t('event.action.' + verb) }}
      </button>
    </template>

    <template v-else>
      <button
        v-if="NEXT_ACTION[event.status] && session.can(PERM[NEXT_ACTION[event.status]!])"
        type="button"
        class="btn primary sm"
        :disabled="busy !== ''"
        @click="run(NEXT_ACTION[event.status]!)"
      >
        {{ t('event.action.' + NEXT_ACTION[event.status]) }}
      </button>
      <button
        v-if="showOpen"
        type="button"
        class="btn sm"
        @click="router.push('/ereignisse/' + event.id)"
      >
        {{ t('event.action.edit') }}
      </button>
    </template>

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
  flex-wrap: wrap;
  gap: 0.4rem;
  align-items: center;
}
.acts--all {
  flex-wrap: nowrap;
  justify-content: flex-end;
}
.acts--all .btn {
  padding: 0.3rem 0.5rem;
  min-height: 1.9rem;
  font-size: 0.72rem;
}
.acts__conflict {
  font-size: 0.78rem;
  color: var(--bbz-warn-text);
}
@media (max-width: 1500px) {
  .acts--all {
    flex-wrap: wrap;
    max-width: 12rem;
  }
}
</style>
