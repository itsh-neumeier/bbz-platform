<script setup lang="ts">
/**
 * Event detail (E07-08 / #107) + ownership (#111), workflow run view (#109),
 * post-processing notes + reactivation (#113 / #115) for an archived event.
 * The same component serves `/ereignisse/:id` and `/archiv/:id`.
 */
import { computed, onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRoute, useRouter } from 'vue-router';
import { useEventsStore } from '@/stores/events';
import { useSessionStore } from '@/stores/session';
import PriorityBadge from '@/components/events/PriorityBadge.vue';
import EventActions from '@/components/events/EventActions.vue';
import OwnershipBar from '@/components/events/OwnershipBar.vue';
import WorkflowRunPanel from '@/components/events/WorkflowRunPanel.vue';
import ReactivateDialog from '@/components/events/ReactivateDialog.vue';

const { t, d } = useI18n();
const route = useRoute();
const router = useRouter();
const events = useEventsStore();
const session = useSessionStore();

const id = computed(() => String(route.params.id));
const detail = computed(() => {
  const raw = events.detail[id.value];
  return raw
    ? { ...raw, notes: raw.notes ?? [], status_history: raw.status_history ?? [] }
    : null;
});
const archived = computed(() => detail.value?.status === 'archived');
const backTo = computed(() => (route.path.startsWith('/archiv') ? '/archiv' : '/ereignisse'));

const notFound = ref(false);
const noteBody = ref('');
const savingNote = ref(false);
const showReactivate = ref(false);

async function load(): Promise<void> {
  notFound.value = false;
  try {
    await events.loadDetail(id.value);
  } catch {
    notFound.value = true;
  }
}

async function saveNote(): Promise<void> {
  if (!noteBody.value.trim()) return;
  savingNote.value = true;
  try {
    await events.addNote(id.value, noteBody.value.trim());
    noteBody.value = '';
  } finally {
    savingNote.value = false;
  }
}

function onReactivated(): void {
  showReactivate.value = false;
  router.push('/ereignisse/' + id.value);
}

onMounted(load);
watch(id, load);
</script>

<template>
  <section class="detail">
    <button
      type="button"
      class="detail__back"
      @click="router.push(backTo)"
    >
      ← {{ t(backTo === '/archiv' ? 'nav.archive' : 'nav.events') }}
    </button>

    <p
      v-if="notFound"
      role="alert"
    >
      {{ t('detail.notFound') }}
    </p>

    <template v-else-if="detail">
      <header class="detail__head">
        <PriorityBadge :priority="detail.priority" />
        <h1>{{ detail.title }}</h1>
        <span class="detail__status">{{ t('event.status.' + detail.status) }}</span>
      </header>

      <EventActions
        v-if="!archived"
        :event="detail"
      />
      <button
        v-else-if="session.can('events.reactivate')"
        type="button"
        class="detail__reactivate"
        @click="showReactivate = true"
      >
        {{ t('reactivate.open') }}
      </button>

      <OwnershipBar :event="detail" />

      <p
        v-if="detail.description"
        class="detail__desc"
      >
        {{ detail.description }}
      </p>

      <div class="detail__grid">
        <section aria-labelledby="hist-h">
          <h2 id="hist-h">
            {{ t('detail.history') }}
          </h2>
          <ol class="detail__hist">
            <li
              v-for="(h, i) in detail.status_history"
              :key="i"
            >
              <span>{{ t('event.status.' + h.to_status) }}</span>
              <time :datetime="h.changed_at">{{ d(new Date(h.changed_at), 'short') }}</time>
            </li>
          </ol>
        </section>

        <WorkflowRunPanel :event-id="detail.id" />

        <section aria-labelledby="notes-h">
          <h2 id="notes-h">
            {{ archived ? t('detail.postprocessNotes') : t('detail.notes') }}
          </h2>
          <ul class="detail__notes">
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
              class="detail__muted"
            >
              {{ t('detail.noNotes') }}
            </li>
          </ul>

          <form
            v-if="session.can('events.note')"
            class="detail__noteform"
            @submit.prevent="saveNote"
          >
            <label for="note-body">{{ t('detail.addNote') }}</label>
            <textarea
              id="note-body"
              v-model="noteBody"
              rows="2"
              maxlength="20000"
            />
            <button
              type="submit"
              :disabled="savingNote || !noteBody.trim()"
            >
              {{ t('detail.saveNote') }}
            </button>
          </form>
        </section>
      </div>
    </template>

    <p
      v-else
      class="detail__muted"
    >
      {{ t('detail.loading') }}
    </p>

    <ReactivateDialog
      :open="showReactivate"
      :event-id="id"
      @close="showReactivate = false"
      @done="onReactivated"
    />
  </section>
</template>

<style scoped>
.detail__back {
  border: 0;
  background: none;
  color: var(--bbz-accent);
  cursor: pointer;
  padding: 0;
  font-size: 0.9rem;
}
.detail__head {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  margin: 0.75rem 0 0.25rem;
}
.detail__head h1 {
  margin: 0;
  font-size: 1.2rem;
}
.detail__status {
  color: var(--bbz-text-muted);
  font-size: 0.85rem;
}
.detail__reactivate {
  padding: 0.35rem 0.8rem;
  border: 1px solid var(--bbz-border);
  border-radius: var(--bbz-radius);
  background: var(--bbz-accent);
  color: #fff;
  cursor: pointer;
}
.detail__desc {
  margin: 0.75rem 0;
  white-space: pre-wrap;
}
.detail__grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(16rem, 1fr));
  gap: 1.5rem;
  margin-top: 1rem;
}
.detail__grid h2 {
  font-size: 0.95rem;
  margin: 0 0 0.5rem;
}
.detail__hist,
.detail__notes {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}
.detail__hist li {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  font-size: 0.85rem;
}
.detail__notes li p {
  margin: 0;
}
.detail__notes time,
.detail__hist time {
  color: var(--bbz-text-muted);
  font-size: 0.78rem;
}
.detail__muted {
  color: var(--bbz-text-muted);
}
.detail__noteform {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  margin-top: 0.75rem;
}
.detail__noteform textarea {
  border: 1px solid var(--bbz-border);
  border-radius: var(--bbz-radius);
  padding: 0.4rem;
  background: var(--bbz-bg);
  color: var(--bbz-text);
  font: inherit;
  resize: vertical;
}
.detail__noteform button {
  align-self: flex-start;
  padding: 0.35rem 0.8rem;
  border: 1px solid var(--bbz-border);
  border-radius: var(--bbz-radius);
  background: var(--bbz-accent);
  color: #fff;
  cursor: pointer;
}
.detail__noteform button:disabled {
  opacity: 0.6;
}
</style>
