<script setup lang="ts">
/**
 * The event processing / work view (MASTER_PROMPT §13.3–13.5): header, the
 * lifecycle actions, ownership, the bound workflow / measures, the status
 * timeline and the notes. Rendered **inline** below the Ereignisspeicher on the
 * Arbeitsplatz (E07-16 / #716) and as the body of the `/ereignisse/:id` and
 * `/archiv/:id` routes (via `EventDetailPage`).
 */
import { computed, onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRouter } from 'vue-router';
import { useEventsStore } from '@/stores/events';
import { useSessionStore } from '@/stores/session';
import PriorityBadge from './PriorityBadge.vue';
import PriorityPulse from './PriorityPulse.vue';
import EventActions from './EventActions.vue';
import OwnershipBar from './OwnershipBar.vue';
import WorkflowRunPanel from './WorkflowRunPanel.vue';
import CameraPanel from './CameraPanel.vue';
import ReactivateDialog from './ReactivateDialog.vue';

const props = withDefaults(
  defineProps<{ eventId: string; standalone?: boolean }>(),
  { standalone: false },
);

const { t, d } = useI18n();
const router = useRouter();
const events = useEventsStore();
const session = useSessionStore();

const detail = computed(() => {
  const raw = events.detail[props.eventId];
  return raw
    ? { ...raw, notes: raw.notes ?? [], status_history: raw.status_history ?? [] }
    : null;
});
const archived = computed(() => detail.value?.status === 'archived');

const notFound = ref(false);
const noteBody = ref('');
const savingNote = ref(false);
const showReactivate = ref(false);

async function load(): Promise<void> {
  notFound.value = false;
  try {
    await events.loadDetail(props.eventId);
  } catch {
    notFound.value = true;
  }
}

async function saveNote(): Promise<void> {
  if (!noteBody.value.trim()) return;
  savingNote.value = true;
  try {
    await events.addNote(props.eventId, noteBody.value.trim(), archived.value ? 'postprocess' : 'work');
    noteBody.value = '';
  } finally {
    savingNote.value = false;
  }
}

function onReactivated(): void {
  showReactivate.value = false;
  void router.push('/ereignisse/' + props.eventId);
}

onMounted(load);
watch(() => props.eventId, load);
</script>

<template>
  <section class="epp">
    <button
      v-if="standalone"
      type="button"
      class="epp__back btn ghost sm"
      @click="router.push(archived ? '/archiv' : '/ereignisse')"
    >
      ← {{ t(archived ? 'nav.archive' : 'nav.events') }}
    </button>

    <p
      v-if="notFound"
      role="alert"
    >
      {{ t('detail.notFound') }}
    </p>

    <template v-else-if="detail">
      <header class="epp__head">
        <PriorityPulse :priority="detail.priority" />
        <PriorityBadge :priority="detail.priority" />
        <h2>{{ detail.title }}</h2>
        <span class="epp__status">{{ t('event.status.' + detail.status) }}</span>
      </header>

      <div class="epp__actions">
        <EventActions
          v-if="!archived"
          :event="detail"
          all
        />
        <button
          v-else-if="session.can('events.reactivate')"
          type="button"
          class="btn db"
          @click="showReactivate = true"
        >
          {{ t('reactivate.open') }}
        </button>
      </div>

      <OwnershipBar :event="detail" />

      <p
        v-if="detail.description"
        class="epp__desc"
      >
        {{ detail.description }}
      </p>

      <div class="epp__grid">
        <section
          class="card"
          aria-labelledby="epp-hist"
        >
          <div class="card-head">
            <div
              id="epp-hist"
              class="card-title"
            >
              {{ t('detail.history') }}
            </div>
          </div>
          <div class="card-body">
            <ol class="epp__hist">
              <li
                v-for="(h, i) in detail.status_history"
                :key="i"
              >
                <span>{{ t('event.status.' + h.to_status) }}</span>
                <time :datetime="h.changed_at">{{ d(new Date(h.changed_at), 'short') }}</time>
              </li>
            </ol>
          </div>
        </section>

        <section class="card epp__wf">
          <div class="card-head">
            <div class="card-title">
              {{ t('workflow.title') }}
            </div>
          </div>
          <div class="card-body">
            <WorkflowRunPanel :event-id="detail.id" />
          </div>
        </section>

        <CameraPanel :event-id="detail.id" />

        <section
          class="card"
          aria-labelledby="epp-notes"
        >
          <div class="card-head">
            <div
              id="epp-notes"
              class="card-title"
            >
              {{ archived ? t('detail.postprocessNotes') : t('detail.notes') }}
            </div>
          </div>
          <div class="card-body">
            <ul class="epp__notes">
              <li
                v-for="n in detail.notes"
                :key="n.id"
              >
                <p>{{ n.body }}</p>
                <time :datetime="n.created_at">
                  {{ d(new Date(n.created_at), 'short') }}
                  <span v-if="n.version > 1">· {{ t('detail.noteVersion', { v: n.version }) }}</span>
                </time>
              </li>
              <li
                v-if="detail.notes.length === 0"
                class="muted"
              >
                {{ t('detail.noNotes') }}
              </li>
            </ul>

            <form
              v-if="session.can('events.postprocess')"
              class="epp__noteform"
              @submit.prevent="saveNote"
            >
              <label :for="'epp-note-' + eventId">{{ t('detail.addNote') }}</label>
              <textarea
                :id="'epp-note-' + eventId"
                v-model="noteBody"
                class="textarea"
                rows="2"
                maxlength="20000"
              />
              <button
                type="submit"
                class="btn primary sm"
                :disabled="savingNote || !noteBody.trim()"
              >
                {{ t('detail.saveNote') }}
              </button>
            </form>
          </div>
        </section>
      </div>
    </template>

    <p
      v-else
      class="muted"
    >
      {{ t('detail.loading') }}
    </p>

    <ReactivateDialog
      :open="showReactivate"
      :event-id="eventId"
      @close="showReactivate = false"
      @done="onReactivated"
    />
  </section>
</template>

<style scoped>
.epp {
  display: grid;
  gap: 0.7rem;
  align-content: start;
}
.epp__back {
  justify-self: start;
}
.epp__head {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}
.epp__head h2 {
  margin: 0;
  font-family: var(--bbz-font-head);
  font-size: 1.1rem;
}
.epp__status {
  color: var(--bbz-text-muted);
  font-size: 0.82rem;
}
.epp__actions {
  display: flex;
  gap: 0.5rem;
}
.epp__desc {
  margin: 0;
  white-space: pre-wrap;
  color: var(--bbz-text);
}
.epp__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(15rem, 1fr));
  gap: 0.75rem;
}
.epp__hist,
.epp__notes {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}
.epp__hist li {
  display: flex;
  justify-content: space-between;
  gap: 0.75rem;
  font-size: 0.82rem;
}
.epp__notes li p {
  margin: 0;
  font-size: 0.85rem;
}
.epp__notes time,
.epp__hist time {
  color: var(--bbz-text-muted);
  font-size: 0.75rem;
}
.epp__noteform {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  margin-top: 0.7rem;
}
.epp__noteform button {
  align-self: flex-start;
}
/* WorkflowRunPanel carries its own <h2> — the card-head already titles it */
.epp__wf :deep(h2) {
  display: none;
}
</style>
