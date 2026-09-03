<script setup lang="ts">
/**
 * Phone-book (E14-07 / #297, E14-08 priority colours / #299, MASTER_PROMPT §13.9).
 * List + substring search (name / org / number) + quick-dial filter, per-contact
 * priority (blau / orange / rot), and CRUD — create, edit fields, manage numbers,
 * assign priority, soft-delete. Every write is permission-gated server-side; the
 * buttons hide when the session lacks the permission.
 */
import { computed, onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { ApiError } from '@/lib/apiClient';
import { useSessionStore } from '@/stores/session';
import {
  contactsApi,
  PRIORITY_CLASS,
  type Contact,
  type ContactPriority,
} from '@/lib/contacts';

const { t } = useI18n();
const session = useSessionStore();

const list = ref<Contact[]>([]);
const q = ref('');
const quickOnly = ref(false);
const loading = ref(false);
const error = ref('');
const selectedId = ref<string | null>(null);
const creating = ref(false);

const selected = computed(() => list.value.find((c) => c.id === selectedId.value) ?? null);
const canCreate = computed(() => session.can('contacts.create'));
const canEdit = computed(() => session.can('contacts.edit'));
const canDelete = computed(() => session.can('contacts.delete'));
const canPrio = computed(() => session.can('contacts.assign_priority'));

const PRIORITIES: ContactPriority[] = ['low', 'medium', 'high'];

let searchToken = 0;
async function load(): Promise<void> {
  const token = ++searchToken;
  loading.value = true;
  error.value = '';
  try {
    const page = await contactsApi.search({
      q: q.value.trim() || undefined,
      quickDial: quickOnly.value || undefined,
      limit: 100,
    });
    if (token !== searchToken) return;
    list.value = page.items;
    if (selectedId.value && !page.items.some((c) => c.id === selectedId.value)) {
      selectedId.value = null;
    }
  } catch (e) {
    if (token === searchToken) error.value = e instanceof ApiError ? e.message : t('phonebook.loadError');
  } finally {
    if (token === searchToken) loading.value = false;
  }
}

let debounce: ReturnType<typeof setTimeout> | undefined;
watch([q, quickOnly], () => {
  clearTimeout(debounce);
  debounce = setTimeout(load, 200);
});

function primaryNumber(c: Contact): string {
  return (c.numbers.find((n) => n.is_primary) ?? c.numbers[0])?.e164 ?? '—';
}

async function reloadOne(id: string): Promise<void> {
  try {
    const fresh = await contactsApi.get(id);
    const i = list.value.findIndex((c) => c.id === id);
    if (i >= 0) list.value[i] = fresh;
  } catch {
    await load();
  }
}

// --- edit ---------------------------------------------------------------
const draft = ref<{ name: string; org: string; notes: string; quick_dial: boolean }>({
  name: '',
  org: '',
  notes: '',
  quick_dial: false,
});
watch(selected, (c) => {
  if (c) draft.value = { name: c.name, org: c.org ?? '', notes: c.notes ?? '', quick_dial: c.quick_dial };
});

async function saveFields(): Promise<void> {
  if (!selected.value) return;
  error.value = '';
  try {
    await contactsApi.update(selected.value.id, {
      name: draft.value.name.trim(),
      org: draft.value.org.trim() || null,
      notes: draft.value.notes.trim() || null,
      quick_dial: draft.value.quick_dial,
    });
    await reloadOne(selected.value.id);
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('phonebook.saveError');
  }
}

async function setPriority(p: ContactPriority): Promise<void> {
  if (!selected.value) return;
  try {
    await contactsApi.setPriority(selected.value.id, p);
    await reloadOne(selected.value.id);
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('phonebook.saveError');
  }
}

async function removeContact(): Promise<void> {
  if (!selected.value) return;
  const id = selected.value.id;
  try {
    await contactsApi.remove(id);
    selectedId.value = null;
    list.value = list.value.filter((c) => c.id !== id);
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('phonebook.saveError');
  }
}

// --- numbers ----------------------------------------------------------
const newNumber = ref('');
async function addNumber(): Promise<void> {
  if (!selected.value || !newNumber.value.trim()) return;
  const id = selected.value.id;
  try {
    await contactsApi.addNumber(id, {
      e164: newNumber.value.trim(),
      is_primary: selected.value.numbers.length === 0,
    });
    newNumber.value = '';
    await reloadOne(id);
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('phonebook.numberError');
  }
}
async function removeNumber(numberId: string): Promise<void> {
  if (!selected.value) return;
  const id = selected.value.id;
  try {
    await contactsApi.removeNumber(id, numberId);
    await reloadOne(id);
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('phonebook.numberError');
  }
}

// --- create ---------------------------------------------------------
const newContact = ref<{ name: string; org: string; number: string }>({ name: '', org: '', number: '' });
async function createContact(): Promise<void> {
  if (!newContact.value.name.trim()) return;
  error.value = '';
  try {
    const created = await contactsApi.create({
      name: newContact.value.name.trim(),
      org: newContact.value.org.trim() || null,
      numbers: newContact.value.number.trim()
        ? [{ e164: newContact.value.number.trim(), is_primary: true }]
        : [],
    });
    newContact.value = { name: '', org: '', number: '' };
    creating.value = false;
    await load();
    selectedId.value = created.id;
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('phonebook.createError');
  }
}

onMounted(load);
</script>

<template>
  <section class="pb">
    <header class="pb__head">
      <h1>{{ t('nav.phonebook') }}</h1>
      <button
        v-if="canCreate"
        type="button"
        class="pb__new"
        @click="creating = !creating"
      >
        {{ t('phonebook.new') }}
      </button>
    </header>

    <form
      class="pb__search"
      role="search"
      @submit.prevent="load"
    >
      <label for="pb-q">{{ t('phonebook.search') }}</label>
      <input
        id="pb-q"
        v-model="q"
        type="search"
        :placeholder="t('phonebook.searchHint')"
        autocomplete="off"
      >
      <label class="pb__check">
        <input
          v-model="quickOnly"
          type="checkbox"
        >
        {{ t('phonebook.quickOnly') }}
      </label>
    </form>

    <p
      v-if="error"
      class="pb__error"
      role="alert"
    >
      {{ error }}
    </p>

    <form
      v-if="creating && canCreate"
      class="pb__create"
      @submit.prevent="createContact"
    >
      <label for="pb-n-name">{{ t('phonebook.name') }}</label>
      <input
        id="pb-n-name"
        v-model="newContact.name"
        required
        maxlength="200"
      >
      <label for="pb-n-org">{{ t('phonebook.org') }}</label>
      <input
        id="pb-n-org"
        v-model="newContact.org"
        maxlength="200"
      >
      <label for="pb-n-num">{{ t('phonebook.number') }}</label>
      <input
        id="pb-n-num"
        v-model="newContact.number"
        placeholder="+49…"
        maxlength="16"
      >
      <button
        type="submit"
        :disabled="!newContact.name.trim()"
      >
        {{ t('phonebook.create') }}
      </button>
    </form>

    <div class="pb__body">
      <ul class="pb__list">
        <li
          v-for="c in list"
          :key="c.id"
        >
          <button
            type="button"
            class="pb__row"
            :class="{ 'pb__row--active': c.id === selectedId }"
            :aria-pressed="c.id === selectedId"
            @click="selectedId = c.id"
          >
            <span
              v-if="c.priority"
              class="pb__prio"
              :class="PRIORITY_CLASS[c.priority]"
              :title="t('phonebook.prio.' + c.priority)"
            />
            <span class="pb__name">{{ c.name }}</span>
            <span
              v-if="c.quick_dial"
              class="pb__star"
              :title="t('phonebook.quick')"
            >★</span>
            <span class="pb__num">{{ primaryNumber(c) }}</span>
            <span
              v-if="c.org"
              class="pb__org"
            >{{ c.org }}</span>
          </button>
        </li>
        <li
          v-if="!loading && list.length === 0"
          class="pb__empty"
        >
          {{ t('phonebook.none') }}
        </li>
      </ul>

      <aside
        v-if="selected"
        class="pb__detail"
        :aria-label="selected.name"
      >
        <h2>{{ selected.name }}</h2>

        <fieldset :disabled="!canEdit">
          <legend>{{ t('phonebook.fields') }}</legend>
          <label for="pb-e-name">{{ t('phonebook.name') }}</label>
          <input
            id="pb-e-name"
            v-model="draft.name"
            maxlength="200"
          >
          <label for="pb-e-org">{{ t('phonebook.org') }}</label>
          <input
            id="pb-e-org"
            v-model="draft.org"
            maxlength="200"
          >
          <label for="pb-e-notes">{{ t('phonebook.notes') }}</label>
          <textarea
            id="pb-e-notes"
            v-model="draft.notes"
            rows="2"
          />
          <label class="pb__check">
            <input
              v-model="draft.quick_dial"
              type="checkbox"
            >
            {{ t('phonebook.quick') }}
          </label>
          <button
            type="button"
            @click="saveFields"
          >
            {{ t('phonebook.save') }}
          </button>
        </fieldset>

        <fieldset v-if="canPrio">
          <legend>{{ t('phonebook.priority') }}</legend>
          <div class="pb__prios">
            <button
              v-for="p in PRIORITIES"
              :key="p"
              type="button"
              class="pb__prio-btn"
              :class="[PRIORITY_CLASS[p], { 'pb__prio-btn--on': selected.priority === p }]"
              :aria-pressed="selected.priority === p"
              @click="setPriority(p)"
            >
              {{ t('phonebook.prio.' + p) }}
            </button>
          </div>
        </fieldset>

        <fieldset>
          <legend>{{ t('phonebook.numbers') }}</legend>
          <ul class="pb__numbers">
            <li
              v-for="n in selected.numbers"
              :key="n.id"
            >
              <span>{{ n.e164 }}</span>
              <span
                v-if="n.is_primary"
                class="pb__primary"
              >{{ t('phonebook.primary') }}</span>
              <button
                v-if="canEdit && selected.numbers.length > 1"
                type="button"
                class="pb__link"
                @click="removeNumber(n.id)"
              >
                {{ t('phonebook.removeNumber') }}
              </button>
            </li>
          </ul>
          <form
            v-if="canEdit"
            class="pb__addnum"
            @submit.prevent="addNumber"
          >
            <label for="pb-addnum">{{ t('phonebook.addNumber') }}</label>
            <input
              id="pb-addnum"
              v-model="newNumber"
              placeholder="+49…"
              maxlength="16"
            >
            <button
              type="submit"
              :disabled="!newNumber.trim()"
            >
              +
            </button>
          </form>
        </fieldset>

        <button
          v-if="canDelete"
          type="button"
          class="pb__delete"
          @click="removeContact"
        >
          {{ t('phonebook.delete') }}
        </button>
      </aside>
    </div>
  </section>
</template>

<style scoped>
.pb__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 1rem;
}
.pb h1 {
  margin: 0 0 0.5rem;
  font-size: 1.25rem;
}
.pb__search {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 1rem;
  margin: 0.5rem 0 1rem;
}
.pb__search input[type='search'] {
  flex: 1 1 16rem;
  padding: 0.4rem;
  border: 1px solid var(--bbz-border);
  border-radius: 4px;
  background: var(--bbz-bg);
  color: var(--bbz-text);
}
.pb__check {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.9rem;
}
.pb__body {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 22rem);
  gap: 1.25rem;
  align-items: start;
}
@media (max-width: 52rem) {
  .pb__body {
    grid-template-columns: 1fr;
  }
}
.pb__list {
  list-style: none;
  margin: 0;
  padding: 0;
  border: 1px solid var(--bbz-border);
  border-radius: 6px;
  overflow: hidden;
}
.pb__row {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  width: 100%;
  padding: 0.5rem 0.75rem;
  border: 0;
  border-bottom: 1px solid var(--bbz-border);
  background: var(--bbz-surface);
  color: var(--bbz-text);
  text-align: left;
  cursor: pointer;
}
.pb__row:last-child {
  border-bottom: 0;
}
.pb__row--active,
.pb__row:hover {
  background: var(--bbz-surface-alt);
}
.pb__row:focus-visible {
  outline: 2px solid var(--bbz-accent);
  outline-offset: -2px;
}
.pb__prio {
  width: 0.7rem;
  height: 0.7rem;
  border-radius: 50%;
  flex: none;
}
.pb__prio-btn {
  padding: 0.3rem 0.6rem;
  border: 1px solid var(--bbz-border);
  border-radius: 4px;
  background: var(--bbz-bg);
  color: var(--bbz-text);
  cursor: pointer;
}
.pb__prio-btn--on {
  outline: 2px solid var(--bbz-accent);
  font-weight: 600;
}
.prio--low {
  background: var(--bbz-prio-low);
}
.prio--medium {
  background: var(--bbz-prio-medium);
}
.prio--high {
  background: var(--bbz-prio-high);
}
.pb__name {
  font-weight: 600;
}
.pb__star {
  color: var(--bbz-warn-text);
}
.pb__num {
  margin-left: auto;
  font-variant-numeric: tabular-nums;
  color: var(--bbz-text-muted);
}
.pb__org {
  color: var(--bbz-text-muted);
  font-size: 0.85rem;
}
.pb__empty,
.pb__none {
  padding: 0.75rem;
  color: var(--bbz-text-muted);
}
.pb__detail {
  border: 1px solid var(--bbz-border);
  border-radius: 6px;
  padding: 1rem;
  background: var(--bbz-surface);
}
.pb__detail h2 {
  margin: 0 0 0.75rem;
  font-size: 1.05rem;
}
.pb__detail fieldset {
  border: 1px solid var(--bbz-border);
  border-radius: 4px;
  margin: 0 0 0.75rem;
  padding: 0.6rem 0.75rem;
}
.pb__detail legend {
  font-size: 0.8rem;
  font-weight: 600;
  padding: 0 0.3rem;
}
.pb__detail label {
  display: block;
  font-size: 0.8rem;
  margin: 0.4rem 0 0.15rem;
}
.pb__detail input,
.pb__detail textarea {
  width: 100%;
  padding: 0.35rem;
  border: 1px solid var(--bbz-border);
  border-radius: 4px;
  background: var(--bbz-bg);
  color: var(--bbz-text);
}
.pb__detail button {
  margin-top: 0.6rem;
  padding: 0.35rem 0.7rem;
  border: 1px solid var(--bbz-border);
  border-radius: 4px;
  background: var(--bbz-bg);
  color: var(--bbz-text);
  cursor: pointer;
}
.pb__prios {
  display: flex;
  gap: 0.4rem;
}
.pb__numbers {
  list-style: none;
  margin: 0;
  padding: 0;
}
.pb__numbers li {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.2rem 0;
  font-variant-numeric: tabular-nums;
}
.pb__primary {
  font-size: 0.7rem;
  text-transform: uppercase;
  color: var(--bbz-text-muted);
}
.pb__link {
  background: none;
  border: 0;
  color: var(--bbz-accent);
  cursor: pointer;
  font-size: 0.8rem;
  margin-left: auto;
}
.pb__addnum {
  display: flex;
  align-items: end;
  gap: 0.4rem;
}
.pb__addnum input {
  flex: 1;
}
.pb__delete {
  color: var(--bbz-danger-text);
}
.pb__error {
  color: var(--bbz-danger-text);
}
.pb__create {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 0.4rem 0.75rem;
  align-items: center;
  border: 1px solid var(--bbz-border);
  border-radius: 6px;
  padding: 0.75rem;
  margin-bottom: 1rem;
  background: var(--bbz-surface);
}
.pb__create input {
  padding: 0.35rem;
  border: 1px solid var(--bbz-border);
  border-radius: 4px;
  background: var(--bbz-bg);
  color: var(--bbz-text);
}
.pb__create button {
  grid-column: 2;
  justify-self: start;
  padding: 0.35rem 0.8rem;
  border: 1px solid var(--bbz-border);
  border-radius: 4px;
  background: var(--bbz-bg);
  color: var(--bbz-text);
  cursor: pointer;
}
</style>
