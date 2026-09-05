<script setup lang="ts">
/**
 * "Wetterereignis erzeugen" confirmation dialog (E18-09 / #391, E18-08 backend).
 *
 * The Wetterlage page opens this instead of calling the API directly: creating a
 * BBZ event from a DWD warning is a deliberate operator action (ADR-0030 — no
 * event without provenance *and* without an operator), so the AC requires a
 * confirmation step. The operator picks the event priority (pre-filled from the
 * DWD warn level) and may add an operational assessment ("betriebliche
 * Bewertung", E18-08's `assessment`). Native <dialog> — esc + focus trap for
 * free, same pattern as CallDocRequiredDialog.vue.
 */
import { nextTick, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { PRIORITIES } from '@/lib/triggers';
import type { EventPriority } from '@/lib/events';
import { suggestPriority, type WeatherAlert } from '@/lib/weather';

const props = defineProps<{
  open: boolean;
  alert: WeatherAlert | null;
  busy: boolean;
  error?: string | null;
}>();
const emit = defineEmits<{
  close: [];
  confirm: [payload: { priority: EventPriority; assessment: string }];
}>();
const { t } = useI18n();

const priority = ref<EventPriority>('medium');
const assessment = ref('');
const dialogEl = ref<HTMLDialogElement | null>(null);

watch(
  () => props.open,
  async (isOpen) => {
    if (!isOpen) {
      dialogEl.value?.close();
      return;
    }
    priority.value = props.alert ? suggestPriority(props.alert.level) : 'medium';
    assessment.value = '';
    await nextTick();
    dialogEl.value?.showModal?.();
    dialogEl.value?.querySelector<HTMLSelectElement>('#wxd-prio')?.focus();
  },
  { immediate: true },
);

function confirm(): void {
  emit('confirm', { priority: priority.value, assessment: assessment.value.trim() });
}
</script>

<template>
  <dialog
    ref="dialogEl"
    class="wxd"
    aria-labelledby="wxd-title"
    @close="emit('close')"
  >
    <form
      class="wxd__form"
      @submit.prevent="confirm"
    >
      <h2 id="wxd-title">
        {{ t('weather.createDialog.title') }}
      </h2>

      <p
        v-if="alert"
        class="wxd__lead"
      >
        <strong>{{ alert.headline || alert.type }}</strong>
        <span class="wxd__region">{{ alert.region }}</span>
      </p>

      <label for="wxd-prio">{{ t('weather.createDialog.priorityLabel') }}</label>
      <select
        id="wxd-prio"
        v-model="priority"
      >
        <option
          v-for="p in PRIORITIES"
          :key="p"
          :value="p"
        >
          {{ t('event.priority.' + p) }}
        </option>
      </select>

      <label for="wxd-assessment">{{ t('weather.createDialog.assessmentLabel') }}</label>
      <textarea
        id="wxd-assessment"
        v-model="assessment"
        rows="3"
        :placeholder="t('weather.createDialog.assessmentHint')"
      />

      <p
        v-if="error"
        role="alert"
        class="wxd__error"
      >
        {{ error }}
      </p>

      <div class="wxd__actions">
        <button
          type="button"
          class="wxd__cancel"
          @click="emit('close')"
        >
          {{ t('weather.createDialog.cancel') }}
        </button>
        <button
          type="submit"
          class="wxd__confirm"
          :disabled="busy"
        >
          {{ t('weather.createDialog.confirm') }}
        </button>
      </div>
    </form>
  </dialog>
</template>

<style scoped>
.wxd {
  width: min(26rem, 92vw);
  border: 1px solid var(--bbz-border);
  border-radius: var(--bbz-radius);
  padding: 0;
  background: var(--bbz-surface);
  color: var(--bbz-text);
}
.wxd::backdrop {
  background: rgb(0 0 0 / 40%);
}
.wxd__form {
  padding: 1.1rem;
  display: flex;
  flex-direction: column;
  gap: 0.55rem;
}
.wxd h2 {
  margin: 0;
  font-size: 1.02rem;
}
.wxd__lead {
  margin: 0;
  font-size: 0.9rem;
}
.wxd__region {
  color: var(--bbz-text-muted);
  font-size: 0.8rem;
  margin-left: 0.4rem;
}
.wxd label {
  font-size: 0.82rem;
  font-weight: 600;
}
.wxd select,
.wxd textarea {
  border: 1px solid var(--bbz-border);
  border-radius: var(--bbz-radius);
  padding: 0.4rem;
  background: var(--bbz-bg);
  color: var(--bbz-text);
  font: inherit;
}
.wxd textarea {
  resize: vertical;
}
.wxd__error {
  margin: 0;
  color: var(--bbz-danger-text);
  font-size: 0.82rem;
}
.wxd__actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  margin-top: 0.3rem;
}
.wxd__cancel,
.wxd__confirm {
  padding: 0.4rem 0.85rem;
  border-radius: var(--bbz-radius);
  cursor: pointer;
  border: 1px solid var(--bbz-border);
  background: var(--bbz-bg);
  color: var(--bbz-text);
}
.wxd__confirm {
  background: var(--bbz-accent);
  color: #fff;
  border-color: transparent;
}
.wxd__confirm:disabled {
  opacity: 0.6;
}
</style>
