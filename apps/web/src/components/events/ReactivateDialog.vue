<script setup lang="ts">
/**
 * Reactivation confirmation dialog (E07-12 / #115). Two-step, matching the
 * backend: fetch a `reactivation-intent` token, then `reactivate` with an
 * explicit confirm + a mandatory reason. Nothing is deleted — the event goes
 * back to `opened`. Uses the native `<dialog>` (esc + focus trap for free).
 */
import { nextTick, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { ApiError } from '@/lib/apiClient';
import { eventsApi } from '@/lib/events';

const props = defineProps<{ open: boolean; eventId: string }>();
const emit = defineEmits<{ close: []; done: [] }>();
const { t } = useI18n();

const reason = ref('');
const token = ref('');
const version = ref(0);
const error = ref('');
const busy = ref(false);
const dialogEl = ref<HTMLDialogElement | null>(null);
const reasonEl = ref<HTMLTextAreaElement | null>(null);

watch(
  () => props.open,
  async (isOpen) => {
    if (!isOpen) {
      dialogEl.value?.close();
      return;
    }
    reason.value = '';
    error.value = '';
    busy.value = true;
    await nextTick();
    dialogEl.value?.showModal?.();
    try {
      const intent = await eventsApi.reactivationIntent(props.eventId);
      token.value = intent.token;
      version.value = intent.event_version;
    } catch (e) {
      error.value = e instanceof ApiError ? e.message : t('login.networkError');
    } finally {
      busy.value = false;
      reasonEl.value?.focus();
    }
  },
  { immediate: true },
);

async function submitReactivation(): Promise<void> {
  if (!reason.value.trim()) {
    error.value = t('reactivate.reasonRequired');
    return;
  }
  busy.value = true;
  error.value = '';
  try {
    await eventsApi.reactivate(props.eventId, token.value, reason.value.trim(), version.value);
    emit('done');
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('login.networkError');
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <dialog
    ref="dialogEl"
    class="rd"
    aria-labelledby="rd-title"
    @close="emit('close')"
  >
    <form
      class="rd__form"
      @submit.prevent="submitReactivation"
    >
      <h2 id="rd-title">
        {{ t('reactivate.title') }}
      </h2>
      <p class="rd__lead">
        {{ t('reactivate.lead') }}
      </p>

      <label for="rd-reason">{{ t('reactivate.reason') }}</label>
      <textarea
        id="rd-reason"
        ref="reasonEl"
        v-model="reason"
        rows="3"
        maxlength="2000"
      />

      <p
        v-if="error"
        class="rd__error"
        role="alert"
      >
        {{ error }}
      </p>

      <div class="rd__actions">
        <button
          type="button"
          class="rd__cancel"
          @click="emit('close')"
        >
          {{ t('reactivate.cancel') }}
        </button>
        <button
          type="submit"
          class="rd__confirm"
          :disabled="busy || !reason.trim()"
          @click="submitReactivation"
        >
          {{ t('reactivate.confirm') }}
        </button>
      </div>
    </form>
  </dialog>
</template>

<style scoped>
.rd {
  width: min(28rem, 92vw);
  border: 1px solid var(--bbz-border);
  border-radius: 8px;
  padding: 0;
  background: var(--bbz-surface);
  color: var(--bbz-text);
}
.rd::backdrop {
  background: rgb(0 0 0 / 40%);
}
.rd__form {
  padding: 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}
.rd h2 {
  margin: 0;
  font-size: 1.05rem;
}
.rd__lead {
  margin: 0;
  color: var(--bbz-text-muted);
  font-size: 0.85rem;
}
.rd textarea {
  border: 1px solid var(--bbz-border);
  border-radius: 4px;
  padding: 0.45rem;
  background: var(--bbz-bg);
  color: var(--bbz-text);
  font: inherit;
  resize: vertical;
}
.rd__error {
  margin: 0;
  color: var(--bbz-danger-text);
  font-size: 0.85rem;
}
.rd__actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
}
.rd__cancel,
.rd__confirm {
  padding: 0.4rem 0.9rem;
  border-radius: 4px;
  cursor: pointer;
  border: 1px solid var(--bbz-border);
  background: var(--bbz-bg);
  color: var(--bbz-text);
}
.rd__confirm {
  background: var(--bbz-accent);
  color: #fff;
  border-color: transparent;
}
.rd__confirm:disabled {
  opacity: 0.6;
}
</style>
