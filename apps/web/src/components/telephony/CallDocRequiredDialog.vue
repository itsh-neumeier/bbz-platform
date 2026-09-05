<script setup lang="ts">
/**
 * Mandatory call-documentation popup (E11-14 / #223). The server already
 * tolerates hanging up without a category — the call just sits in
 * `ended_pending_documentation` until someone documents it later (E11-10) —
 * but leaving that to "later" means it is easy to forget. This catches it
 * *before* the hangup: `CommsSidebar` opens it instead of calling hangup
 * directly whenever `calls.docRequired` is true. Cancelling leaves the call
 * exactly as it was (still active, not hung up) — the popup gates the
 * *hangup*, not itself; there is no way to complete it without a category.
 * Native <dialog> (esc + focus trap for free, same pattern as
 * ReactivateDialog.vue).
 */
import { nextTick, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { CALL_CATEGORIES, type CallCategory } from '@/lib/telephony';

const props = defineProps<{ open: boolean; busy: boolean }>();
const emit = defineEmits<{ close: []; confirm: [category: CallCategory, freeText: string] }>();
const { t } = useI18n();

const category = ref<CallCategory | ''>('');
const freeText = ref('');
const dialogEl = ref<HTMLDialogElement | null>(null);

watch(
  () => props.open,
  async (isOpen) => {
    if (!isOpen) {
      dialogEl.value?.close();
      return;
    }
    category.value = '';
    freeText.value = '';
    await nextTick();
    dialogEl.value?.showModal?.();
    dialogEl.value?.querySelector<HTMLInputElement>('input[type="radio"]')?.focus();
  },
  { immediate: true },
);

function confirm(): void {
  if (!category.value) return;
  emit('confirm', category.value, freeText.value);
}
</script>

<template>
  <dialog
    ref="dialogEl"
    class="cdd"
    aria-labelledby="cdd-title"
    @close="emit('close')"
  >
    <form
      class="cdd__form"
      @submit.prevent="confirm"
    >
      <h2 id="cdd-title">
        {{ t('comms.docDialog.title') }}
      </h2>
      <p class="cdd__lead">
        {{ t('comms.docDialog.lead') }}
      </p>

      <fieldset>
        <legend>{{ t('comms.category') }}</legend>
        <label
          v-for="cat in CALL_CATEGORIES"
          :key="cat"
          class="cdd__cat"
        >
          <input
            v-model="category"
            type="radio"
            name="cdd-cat"
            :value="cat"
          >
          {{ t('comms.cat.' + cat) }}
        </label>
      </fieldset>

      <label for="cdd-free">{{ t('comms.freeText') }}</label>
      <textarea
        id="cdd-free"
        v-model="freeText"
        rows="2"
      />

      <div class="cdd__actions">
        <button
          type="button"
          class="cdd__cancel"
          @click="emit('close')"
        >
          {{ t('comms.docDialog.cancel') }}
        </button>
        <button
          type="submit"
          class="cdd__confirm"
          :disabled="busy || !category"
        >
          {{ t('comms.docDialog.confirm') }}
        </button>
      </div>
    </form>
  </dialog>
</template>

<style scoped>
.cdd {
  width: min(24rem, 92vw);
  border: 1px solid var(--bbz-border);
  border-radius: var(--bbz-radius);
  padding: 0;
  background: var(--bbz-surface);
  color: var(--bbz-text);
}
.cdd::backdrop {
  background: rgb(0 0 0 / 40%);
}
.cdd__form {
  padding: 1.1rem;
  display: flex;
  flex-direction: column;
  gap: 0.55rem;
}
.cdd h2 {
  margin: 0;
  font-size: 1.02rem;
}
.cdd__lead {
  margin: 0;
  color: var(--bbz-text-muted);
  font-size: 0.85rem;
}
.cdd fieldset {
  border: 1px solid var(--bbz-border);
  border-radius: var(--bbz-radius);
  margin: 0;
  padding: 0.5rem 0.7rem;
}
.cdd legend {
  font-size: 0.8rem;
  font-weight: 600;
  padding: 0 0.3rem;
}
.cdd__cat {
  display: block;
  font-size: 0.88rem;
  padding: 0.15rem 0;
}
.cdd label:not(.cdd__cat) {
  font-size: 0.85rem;
}
.cdd textarea {
  border: 1px solid var(--bbz-border);
  border-radius: var(--bbz-radius);
  padding: 0.4rem;
  background: var(--bbz-bg);
  color: var(--bbz-text);
  font: inherit;
  resize: vertical;
}
.cdd__actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
  margin-top: 0.3rem;
}
.cdd__cancel,
.cdd__confirm {
  padding: 0.4rem 0.85rem;
  border-radius: var(--bbz-radius);
  cursor: pointer;
  border: 1px solid var(--bbz-border);
  background: var(--bbz-bg);
  color: var(--bbz-text);
}
.cdd__confirm {
  background: var(--bbz-accent);
  color: #fff;
  border-color: transparent;
}
.cdd__confirm:disabled {
  opacity: 0.6;
}
</style>
