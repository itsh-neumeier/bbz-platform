<script setup lang="ts">
/**
 * Quick-dial overlay (E11-15 / #225). A dedicated "Kurzwahl öffnen" button in
 * the Telefon tab opens this instead of a permanent quick-dial grid taking up
 * layout space (MASTER_PROMPT §13.11's own AC: "kein Dauergitter im
 * Layout"). Lists contacts flagged `quick_dial` (E14-06); choosing one hands
 * the contact back to the parent, which dials it (`CommsSidebar.vue` already
 * has that logic via `dialContact`) and this overlay just closes. Native
 * <dialog> (esc + focus trap for free), same pattern as ReactivateDialog.vue
 * / CallDocRequiredDialog.vue.
 */
import { nextTick, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { contactsApi, PRIORITY_CLASS, type Contact } from '@/lib/contacts';

const props = defineProps<{ open: boolean }>();
const emit = defineEmits<{ close: []; dial: [contact: Contact] }>();
const { t } = useI18n();

const dialogEl = ref<HTMLDialogElement | null>(null);
const contacts = ref<Contact[]>([]);
const loading = ref(false);
const failed = ref(false);

watch(
  () => props.open,
  async (isOpen) => {
    if (!isOpen) {
      dialogEl.value?.close();
      return;
    }
    loading.value = true;
    failed.value = false;
    try {
      const page = await contactsApi.search({ quickDial: true, limit: 50 });
      contacts.value = page.items;
    } catch {
      contacts.value = [];
      failed.value = true;
    } finally {
      loading.value = false;
    }
    await nextTick();
    dialogEl.value?.showModal?.();
    dialogEl.value?.querySelector<HTMLButtonElement>('.qd__item')?.focus();
  },
  { immediate: true },
);

function primaryNumber(c: Contact): string | undefined {
  return (c.numbers.find((n) => n.is_primary) ?? c.numbers[0])?.e164;
}

function choose(c: Contact): void {
  if (!primaryNumber(c)) return;
  emit('dial', c);
}
</script>

<template>
  <dialog
    ref="dialogEl"
    class="qd"
    aria-labelledby="qd-title"
    @close="emit('close')"
  >
    <div class="qd__body">
      <h2 id="qd-title">
        {{ t('comms.quickDial.title') }}
      </h2>

      <p
        v-if="loading"
        class="qd__muted"
      >
        {{ t('comms.quickDial.loading') }}
      </p>
      <p
        v-else-if="failed"
        class="qd__muted"
      >
        {{ t('comms.quickDial.error') }}
      </p>
      <p
        v-else-if="!contacts.length"
        class="qd__muted"
      >
        {{ t('comms.quickDial.empty') }}
      </p>

      <ul
        v-else
        class="qd__list"
      >
        <li
          v-for="c in contacts"
          :key="c.id"
        >
          <button
            type="button"
            class="qd__item"
            :disabled="!primaryNumber(c)"
            @click="choose(c)"
          >
            <span
              v-if="c.priority"
              class="qd__prio"
              :class="PRIORITY_CLASS[c.priority]"
              :title="t('comms.prio.' + c.priority)"
            />
            <span class="qd__name">{{ c.name }}</span>
            <span
              v-if="c.org"
              class="qd__org"
            >{{ c.org }}</span>
            <span class="qd__num">{{ primaryNumber(c) ?? '—' }}</span>
          </button>
        </li>
      </ul>

      <div class="qd__actions">
        <button
          type="button"
          class="qd__cancel"
          @click="emit('close')"
        >
          {{ t('comms.quickDial.cancel') }}
        </button>
      </div>
    </div>
  </dialog>
</template>

<style scoped>
.qd {
  width: min(22rem, 92vw);
  max-height: min(28rem, 80vh);
  border: 1px solid var(--bbz-border);
  border-radius: var(--bbz-radius);
  padding: 1.1rem;
  background: var(--bbz-surface);
  color: var(--bbz-text);
}
.qd::backdrop {
  background: rgb(0 0 0 / 40%);
}
/* NOT on `.qd` itself: a `display` there would override the native
   `dialog:not([open]) { display: none }` UA rule (author styles always win
   over user-agent styles regardless of specificity), permanently defeating
   `showModal()`/`close()`'s own visibility toggle. Same reason
   CallDocRequiredDialog.vue/ReactivateDialog.vue put their flex layout on an
   inner wrapper, not the <dialog> element. */
.qd__body {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}
.qd h2 {
  margin: 0;
  font-size: 1.02rem;
}
.qd__muted {
  margin: 0;
  color: var(--bbz-text-muted);
  font-size: 0.9rem;
}
.qd__list {
  list-style: none;
  margin: 0;
  padding: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}
.qd__item {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.6rem;
  border: 1px solid var(--bbz-border);
  border-radius: var(--bbz-radius);
  background: var(--bbz-bg);
  color: var(--bbz-text);
  cursor: pointer;
  text-align: left;
}
.qd__item:hover,
.qd__item:focus-visible {
  border-color: var(--bbz-accent);
}
.qd__item:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.qd__prio {
  width: 0.7rem;
  height: 0.7rem;
  border-radius: 50%;
  flex: none;
}
.qd__prio.prio--low {
  background: var(--bbz-prio-low);
}
.qd__prio.prio--medium {
  background: var(--bbz-prio-medium);
}
.qd__prio.prio--high {
  background: var(--bbz-prio-high);
}
.qd__name {
  font-weight: 600;
}
.qd__org,
.qd__num {
  color: var(--bbz-text-muted);
  font-size: 0.85rem;
}
.qd__num {
  margin-left: auto;
  font-variant-numeric: tabular-nums;
}
.qd__actions {
  display: flex;
  justify-content: flex-end;
}
.qd__cancel {
  padding: 0.4rem 0.85rem;
  border-radius: var(--bbz-radius);
  cursor: pointer;
  border: 1px solid var(--bbz-border);
  background: var(--bbz-bg);
  color: var(--bbz-text);
}
</style>
