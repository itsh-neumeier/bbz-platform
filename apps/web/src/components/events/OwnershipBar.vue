<script setup lang="ts">
/**
 * Full-event ownership (E07-10 / #111): who holds it, take it over, hand it to
 * a named operator, and the operator's own presence.
 */
import { computed, onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { api, ConflictError } from '@/lib/apiClient';
import { eventsApi, type EventDetail } from '@/lib/events';
import { useEventsStore } from '@/stores/events';
import { useSessionStore } from '@/stores/session';

const props = defineProps<{ event: EventDetail }>();
const { t } = useI18n();
const events = useEventsStore();
const session = useSessionStore();

const busy = ref(false);
const conflict = ref(false);
const presence = ref<string>('');
const people = ref<{ id: string; display_name: string }[]>([]);

const active = computed(() => props.event.status !== 'archived');
const mine = computed(() => props.event.assignee_id === session.user?.id);
const canTakeover = computed(() => active.value && session.can('events.takeover') && !mine.value);
const canAssign = computed(() => active.value && session.can('events.assign'));

async function takeover(): Promise<void> {
  busy.value = true;
  conflict.value = false;
  try {
    await eventsApi.takeover(props.event.id, props.event.version);
    await events.loadDetail(props.event.id);
  } catch (e) {
    if (e instanceof ConflictError) {
      conflict.value = true;
      await events.loadDetail(props.event.id).catch(() => undefined);
    }
  } finally {
    busy.value = false;
  }
}

async function assign(targetUserId: string): Promise<void> {
  if (!targetUserId) return;
  busy.value = true;
  conflict.value = false;
  try {
    await eventsApi.assign(props.event.id, targetUserId, props.event.version);
    await events.loadDetail(props.event.id);
  } catch (e) {
    if (e instanceof ConflictError) {
      conflict.value = true;
      await events.loadDetail(props.event.id).catch(() => undefined);
    }
  } finally {
    busy.value = false;
  }
}

async function setPresence(state: string): Promise<void> {
  presence.value = state;
  await api.put('/presence', { state }).catch(() => undefined);
}

onMounted(async () => {
  try {
    presence.value = (await api.get<{ state: string }>('/presence/me')).state;
  } catch {
    /* presence is optional context */
  }
  if (session.can('events.assign')) {
    try {
      people.value = (await eventsApi.assignable()).users;
    } catch {
      /* the roster is optional — takeover still works */
    }
  }
});
</script>

<template>
  <div class="own">
    <span class="own__assignee">
      {{ t('ownership.assignee') }}:
      <strong>{{ mine ? t('ownership.you') : event.assignee_id ? t('ownership.other') : t('ownership.none') }}</strong>
    </span>

    <button
      v-if="canTakeover"
      type="button"
      class="own__btn"
      :disabled="busy"
      @click="takeover"
    >
      {{ t('ownership.takeover') }}
    </button>

    <span
      v-if="canAssign && people.length"
      class="own__assign"
    >
      {{ t('ownership.assignTo') }}:
      <select
        :value="''"
        :aria-label="t('ownership.assignTo')"
        :disabled="busy"
        @change="assign(($event.target as HTMLSelectElement).value)"
      >
        <option value="">
          {{ t('ownership.pickPerson') }}
        </option>
        <option
          v-for="p in people"
          :key="p.id"
          :value="p.id"
        >
          {{ p.display_name }}
        </option>
      </select>
    </span>

    <span class="own__presence">
      {{ t('ownership.presence') }}:
      <select
        :value="presence"
        :aria-label="t('ownership.presence')"
        @change="setPresence(($event.target as HTMLSelectElement).value)"
      >
        <option value="available">{{ t('presence.available') }}</option>
        <option value="busy">{{ t('presence.busy') }}</option>
        <option value="away">{{ t('presence.away') }}</option>
      </select>
    </span>

    <span
      v-if="conflict"
      class="own__conflict"
      role="alert"
    >{{ t('event.conflict') }}</span>
  </div>
</template>

<style scoped>
.own {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem;
  padding: 0.5rem 0;
  font-size: 0.85rem;
  color: var(--bbz-text-muted);
}
.own__btn {
  padding: 0.25rem 0.6rem;
  border: 1px solid var(--bbz-border);
  border-radius: var(--bbz-radius);
  background: var(--bbz-bg);
  color: var(--bbz-text);
  cursor: pointer;
}
.own__btn:disabled {
  opacity: 0.6;
}
.own select {
  border: 1px solid var(--bbz-border);
  border-radius: var(--bbz-radius);
  padding: 0.15rem 0.3rem;
  background: var(--bbz-bg);
  color: var(--bbz-text);
}
.own__conflict {
  color: var(--bbz-warn-text);
}
</style>
