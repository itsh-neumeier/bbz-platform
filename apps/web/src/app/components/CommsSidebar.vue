<script setup lang="ts">
/**
 * Comms sidebar (E07-18 / #127 + Epic 11 UI — E11-13/14/15, MASTER_PROMPT §13.8–13.11).
 * Four tabs: Telefon (keypad + line + waiting-call queue + a "Kurzwahl öffnen"
 * button — no permanent quick-dial grid, E11-15 / #225), Gespräch (active-call
 * controls + mandatory documentation), Telefonbuch (search + quick-dial → dial),
 * Historie (recent calls). Horizontally resizable with a keyboard-operable handle
 * — operation must never rely on drag alone (RULES.md §a11y). The waiting-call
 * queue is priority-coloured with a pulse that stills under `prefers-reduced-motion`.
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useSessionStore } from '@/stores/session';
import { useCallsStore } from '@/stores/calls';
import { useReducedMotion } from '@/composables/useReducedMotion';
import { CALL_CATEGORIES, otherParty, type CallCategory } from '@/lib/telephony';
import { contactsApi, type Contact } from '@/lib/contacts';
import CallDocRequiredDialog from '@/components/telephony/CallDocRequiredDialog.vue';
import QuickDialOverlay from '@/components/telephony/QuickDialOverlay.vue';

const { t } = useI18n();
const session = useSessionStore();
const calls = useCallsStore();
const { reduced } = useReducedMotion();

const TABS = ['phone', 'call', 'phonebook', 'history'] as const;
type Tab = (typeof TABS)[number];
const tab = ref<Tab>('phone');

const canDial = computed(() => session.can('calls.dial'));
const canAnswer = computed(() => session.can('calls.answer'));
const canHangup = computed(() => session.can('calls.hangup'));
const canHold = computed(() => session.can('calls.hold'));
const canTransfer = computed(() => session.can('calls.transfer'));
const canDocument = computed(() => session.can('calls.document'));

// --- call duration (E11-13 / #221) -----------------------------------
const clockNow = ref(Date.now());
let clockTimer: ReturnType<typeof setInterval> | undefined;
onMounted(() => {
  clockTimer = setInterval(() => {
    clockNow.value = Date.now();
  }, 1000);
});
onBeforeUnmount(() => clearInterval(clockTimer));

/** mm:ss since the call connected; freezes once it has ended (still shown
 *  while `ended_pending_documentation`, per docRequired). */
const duration = computed(() => {
  const c = calls.active;
  if (!c?.started_at) return null;
  const started = new Date(c.started_at).getTime();
  const end = c.ended_at ? new Date(c.ended_at).getTime() : clockNow.value;
  const secs = Math.max(0, Math.floor((end - started) / 1000));
  const m = Math.floor(secs / 60);
  const s = secs % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
});

// --- resize handle ---------------------------------------------------
const dragging = ref(false);
const STEP = 16;
function onPointerDown(e: PointerEvent) {
  dragging.value = true;
  (e.target as HTMLElement).setPointerCapture(e.pointerId);
}
function onPointerMove(e: PointerEvent) {
  if (!dragging.value) return;
  session.setCommsWidth(window.innerWidth - e.clientX);
}
function onPointerUp() {
  dragging.value = false;
}
function onKey(e: KeyboardEvent) {
  if (e.key === 'ArrowLeft') session.setCommsWidth(session.commsWidth + STEP);
  else if (e.key === 'ArrowRight') session.setCommsWidth(session.commsWidth - STEP);
}
onBeforeUnmount(onPointerUp);

// --- dial pad -------------------------------------------------------
const dialInput = ref('');
const selectedLine = ref('');
const KEYS = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '*', '0', '#'];
const serviceableLines = computed(() => calls.lines.filter((l) => l.state === 'in_service'));

function press(k: string) {
  dialInput.value += k;
}
function backspace() {
  dialInput.value = dialInput.value.slice(0, -1);
}
async function doDial() {
  const line = selectedLine.value || serviceableLines.value[0]?.id;
  if (!line || !dialInput.value.trim()) return;
  await calls.dial(line, dialInput.value.trim());
  dialInput.value = '';
  if (calls.active) tab.value = 'call';
}

async function answer(id: string) {
  await calls.control('answer', id);
  tab.value = 'call';
}

// --- transfer ------------------------------------------------------
const transferTo = ref('');
async function doTransfer() {
  if (!calls.active || !transferTo.value.trim()) return;
  await calls.transfer(calls.active.id, transferTo.value.trim());
  transferTo.value = '';
}

// --- documentation ----------------------------------------------
const docCategory = ref<CallCategory | ''>('');
const docText = ref('');
async function saveDoc() {
  await calls.saveDoc(docCategory.value || null, docText.value);
}
function syncDocForm() {
  docCategory.value = calls.doc?.category ?? '';
  docText.value = calls.doc?.free_text ?? '';
}
// keep the form in step when the doc (re)loads for a new active call
watch(() => calls.doc, syncDocForm);

// --- mandatory-documentation hangup gate (E11-14 / #223) -------------
// Hanging up without a category is not itself an error — the server just
// parks the call in `ended_pending_documentation` (E11-10) — but leaving
// that to "whenever someone notices the badge" is easy to forget. Catch it
// *before* the hangup instead: intercept the click, only actually hang up
// once a category has been chosen.
const showDocGate = ref(false);
function requestHangup(): void {
  if (!calls.active) return;
  if (calls.docRequired) {
    showDocGate.value = true;
    return;
  }
  void calls.control('hangup', calls.active.id);
}
async function confirmDocAndHangup(category: CallCategory, freeText: string): Promise<void> {
  if (!calls.active) return;
  await calls.saveDoc(category, freeText);
  if (calls.active) await calls.control('hangup', calls.active.id);
  showDocGate.value = false;
}

// --- phonebook mini -------------------------------------------
const pbQuery = ref('');
const pbResults = ref<Contact[]>([]);
let pbTimer: ReturnType<typeof setTimeout> | undefined;
function pbSearch() {
  clearTimeout(pbTimer);
  pbTimer = setTimeout(async () => {
    try {
      const page = await contactsApi.search({
        q: pbQuery.value.trim() || undefined,
        quickDial: pbQuery.value.trim() ? undefined : true,
        limit: 30,
      });
      pbResults.value = page.items;
    } catch {
      pbResults.value = [];
    }
  }, 200);
}
async function dialContact(c: Contact) {
  const num = (c.numbers.find((n) => n.is_primary) ?? c.numbers[0])?.e164;
  if (!num) return;
  dialInput.value = num;
  tab.value = 'phone';
  await doDial();
}

// --- quick-dial overlay (E11-15 / #225) -------------------------------
const showQuickDial = ref(false);
async function dialFromQuickDial(c: Contact): Promise<void> {
  showQuickDial.value = false;
  await dialContact(c);
}

let poll: ReturnType<typeof setInterval> | undefined;
onMounted(async () => {
  await calls.refresh();
  syncDocForm();
  pbSearch();
  // slow safety poll; the SSE stream is the primary signal (AppShell wires it).
  poll = setInterval(() => void calls.refresh().then(syncDocForm), 20_000);
});
onBeforeUnmount(() => clearInterval(poll));
</script>

<template>
  <aside
    class="comms"
    :aria-label="t('comms.phone')"
  >
    <button
      class="comms__handle"
      type="button"
      role="separator"
      :aria-label="t('comms.resize')"
      aria-orientation="vertical"
      aria-valuemin="280"
      aria-valuemax="640"
      :aria-valuenow="session.commsWidth"
      @pointerdown="onPointerDown"
      @pointermove="onPointerMove"
      @pointerup="onPointerUp"
      @keydown="onKey"
    />

    <div
      class="comms__tabs"
      role="tablist"
      :aria-label="t('comms.phone')"
    >
      <button
        v-for="tb in TABS"
        :key="tb"
        type="button"
        role="tab"
        :aria-selected="tab === tb"
        :class="{ 'comms__tab--on': tab === tb }"
        class="comms__tab"
        @click="tab = tb"
      >
        {{ t('comms.' + tb) }}
        <span
          v-if="tb === 'call' && calls.pendingDocCount"
          class="comms__badge"
        >{{ calls.pendingDocCount }}</span>
        <span
          v-if="tb === 'phone' && calls.ringing.length"
          class="comms__badge comms__badge--live"
        >{{ calls.ringing.length }}</span>
      </button>
    </div>

    <p
      v-if="calls.error"
      class="comms__error"
      role="alert"
    >
      {{ calls.error }}
    </p>

    <!-- TELEFON ---------------------------------------------------->
    <div
      v-show="tab === 'phone'"
      role="tabpanel"
      class="comms__panel"
    >
      <div
        v-if="canDial"
        class="tp"
      >
        <label
          v-if="serviceableLines.length > 1"
          for="tp-line"
        >{{ t('comms.line') }}</label>
        <select
          v-if="serviceableLines.length > 1"
          id="tp-line"
          v-model="selectedLine"
        >
          <option
            v-for="l in serviceableLines"
            :key="l.id"
            :value="l.id"
          >
            {{ l.label ?? l.external_id }}
          </option>
        </select>

        <label
          for="tp-input"
          class="tp__srlabel"
        >{{ t('comms.number') }}</label>
        <input
          id="tp-input"
          v-model="dialInput"
          class="tp__display"
          inputmode="tel"
          :placeholder="t('comms.number')"
        >
        <div class="tp__pad">
          <button
            v-for="k in KEYS"
            :key="k"
            type="button"
            class="tp__key"
            @click="press(k)"
          >
            {{ k }}
          </button>
        </div>
        <div class="tp__row">
          <button
            type="button"
            :disabled="!dialInput"
            @click="backspace"
          >
            ⌫
          </button>
          <button
            type="button"
            class="tp__call"
            :disabled="calls.busy || !dialInput.trim() || !serviceableLines.length"
            @click="doDial"
          >
            {{ t('comms.dial') }}
          </button>
        </div>

        <button
          type="button"
          class="tp__quickdial"
          @click="showQuickDial = true"
        >
          {{ t('comms.quickDial.open') }}
        </button>
      </div>

      <h3 class="comms__h">
        {{ t('comms.waiting') }}
      </h3>
      <ul class="wq">
        <li
          v-for="c in calls.sortedRinging"
          :key="c.id"
          class="wq__item"
          :class="[
            'wq__item--' + (c.caller_priority ?? 'unknown'),
            { 'wq__item--still': reduced },
          ]"
        >
          <span class="wq__who">{{ otherParty(c) }}</span>
          <span
            v-if="c.caller_priority"
            class="wq__prio"
          >{{ t('comms.prio.' + c.caller_priority) }}</span>
          <button
            v-if="canAnswer"
            type="button"
            class="wq__answer"
            :disabled="calls.busy"
            @click="answer(c.id)"
          >
            {{ t('comms.answer') }}
          </button>
        </li>
        <li
          v-if="!calls.ringing.length"
          class="comms__muted"
        >
          {{ t('comms.noWaiting') }}
        </li>
      </ul>
    </div>

    <!-- GESPRÄCH ------------------------------------------------->
    <div
      v-show="tab === 'call'"
      role="tabpanel"
      class="comms__panel"
    >
      <div v-if="calls.active">
        <div class="ac">
          <span class="ac__who">{{ otherParty(calls.active) }}</span>
          <span
            v-if="duration"
            class="ac__duration"
          >{{ duration }}</span>
          <span class="ac__state">{{ t('comms.state.' + calls.active.state) }}</span>
        </div>

        <p
          v-if="calls.docRequired"
          class="ac__docreq"
          role="alert"
        >
          {{ t('comms.docRequired') }}
        </p>

        <div class="ac__controls">
          <button
            v-if="canHold && calls.active.state === 'connected'"
            type="button"
            :disabled="calls.busy"
            @click="calls.control('hold', calls.active.id)"
          >
            {{ t('comms.hold') }}
          </button>
          <button
            v-if="canHold && calls.active.state === 'held'"
            type="button"
            :disabled="calls.busy"
            @click="calls.control('resume', calls.active.id)"
          >
            {{ t('comms.resume') }}
          </button>
          <button
            v-if="canHangup"
            type="button"
            class="ac__hangup"
            :disabled="calls.busy"
            @click="requestHangup"
          >
            {{ t('comms.hangup') }}
          </button>
        </div>

        <form
          v-if="canTransfer"
          class="ac__transfer"
          @submit.prevent="doTransfer"
        >
          <label for="ac-xfer">{{ t('comms.transfer') }}</label>
          <input
            id="ac-xfer"
            v-model="transferTo"
            placeholder="+49…"
          >
          <button
            type="submit"
            :disabled="calls.busy || !transferTo.trim()"
          >
            →
          </button>
        </form>

        <form
          v-if="canDocument"
          class="ac__doc"
          @submit.prevent="saveDoc"
        >
          <fieldset>
            <legend>{{ t('comms.category') }}</legend>
            <label
              v-for="cat in CALL_CATEGORIES"
              :key="cat"
              class="ac__cat"
            >
              <input
                v-model="docCategory"
                type="radio"
                name="callcat"
                :value="cat"
              >
              {{ t('comms.cat.' + cat) }}
            </label>
          </fieldset>
          <label for="ac-free">{{ t('comms.freeText') }}</label>
          <textarea
            id="ac-free"
            v-model="docText"
            rows="2"
          />
          <button
            type="submit"
            :disabled="calls.busy"
          >
            {{ t('comms.saveDoc') }}
          </button>
        </form>
      </div>
      <p
        v-else
        class="comms__muted"
      >
        {{ t('comms.noActive') }}
      </p>
    </div>

    <!-- TELEFONBUCH -------------------------------------------->
    <div
      v-show="tab === 'phonebook'"
      role="tabpanel"
      class="comms__panel"
    >
      <label
        for="pb-mini"
        class="tp__srlabel"
      >{{ t('comms.search') }}</label>
      <input
        id="pb-mini"
        v-model="pbQuery"
        type="search"
        :placeholder="t('comms.search')"
        @input="pbSearch"
      >
      <ul class="mini">
        <li
          v-for="c in pbResults"
          :key="c.id"
        >
          <button
            type="button"
            class="mini__row"
            :disabled="!canDial || !c.numbers.length"
            @click="dialContact(c)"
          >
            <span
              v-if="c.priority"
              class="mini__prio"
              :class="'prio--' + c.priority"
            />
            <span class="mini__name">{{ c.name }}</span>
            <span class="mini__num">{{ (c.numbers.find((n) => n.is_primary) ?? c.numbers[0])?.e164 ?? '—' }}</span>
          </button>
        </li>
        <li
          v-if="!pbResults.length"
          class="comms__muted"
        >
          {{ t('comms.noContacts') }}
        </li>
      </ul>
    </div>

    <!-- HISTORIE ---------------------------------------------->
    <div
      v-show="tab === 'history'"
      role="tabpanel"
      class="comms__panel"
    >
      <ul class="hist">
        <li
          v-for="c in calls.history"
          :key="c.id"
          class="hist__item"
        >
          <span
            class="hist__dir"
            :title="t('comms.dir.' + c.direction)"
          >{{ c.direction === 'inbound' ? '↙' : '↗' }}</span>
          <span class="hist__who">{{ otherParty(c) }}</span>
          <span
            v-if="c.category"
            class="hist__cat"
          >{{ t('comms.cat.' + c.category) }}</span>
          <span class="hist__time">{{ (c.started_at ?? c.created_at).slice(11, 16) }}</span>
        </li>
        <li
          v-if="!calls.history.length"
          class="comms__muted"
        >
          {{ t('comms.noHistory') }}
        </li>
      </ul>
    </div>

    <div class="comms__lines">
      <span
        v-for="l in calls.lines"
        :key="l.id"
        class="comms__line"
        :class="{ 'comms__line--down': l.state !== 'in_service' }"
        :title="l.label ?? l.external_id"
      >{{ l.label ?? l.external_id }}</span>
    </div>

    <CallDocRequiredDialog
      :open="showDocGate"
      :busy="calls.busy"
      @close="showDocGate = false"
      @confirm="confirmDocAndHangup"
    />
    <QuickDialOverlay
      :open="showQuickDial"
      @close="showQuickDial = false"
      @dial="dialFromQuickDial"
    />
  </aside>
</template>

<style scoped>
.comms {
  position: relative;
  display: flex;
  flex-direction: column;
  padding: 0.5rem 0.75rem 0.5rem 1rem;
  gap: 0.5rem;
  width: 100%;
  min-width: 0;
  height: 100%;
  overflow: auto;
  background: var(--bbz-bg);
}
.comms__handle {
  position: absolute;
  left: -5px;
  top: 0;
  bottom: 0;
  width: 12px;
  padding: 0;
  border: 0;
  cursor: col-resize;
  background: transparent;
  z-index: 5;
}
.comms__handle::before {
  content: '';
  position: absolute;
  left: 5px;
  top: 0;
  bottom: 0;
  width: 2px;
  background: transparent;
  transition: background-color var(--bbz-transition);
}
.comms__handle:hover::before,
.comms__handle:focus-visible::before {
  background: var(--bbz-info);
}
.comms__handle:focus-visible {
  outline: var(--bbz-focus-width) solid var(--bbz-focus-color);
}
.comms__tabs {
  display: flex;
  gap: 0.15rem;
}
.comms__tab {
  flex: 1;
  padding: 0.35rem 0.2rem;
  border: 1px solid var(--bbz-border);
  border-bottom: 0;
  border-radius: var(--bbz-radius) 4px 0 0;
  background: var(--bbz-surface-alt);
  color: var(--bbz-text-muted);
  font-size: 0.78rem;
  cursor: pointer;
}
.comms__tab--on {
  background: var(--bbz-surface);
  color: var(--bbz-text);
  font-weight: 600;
}
.comms__tab:focus-visible {
  outline: var(--bbz-focus-width) solid var(--bbz-focus-color);
}
.comms__badge {
  display: inline-block;
  min-width: 1.1em;
  padding: 0 0.25em;
  border-radius: 999px;
  background: var(--bbz-text-muted);
  color: var(--bbz-surface);
  font-size: 0.7rem;
}
.comms__badge--live {
  background: var(--bbz-prio-high);
  color: #fff;
}
.comms__panel {
  flex: 1;
  overflow: auto;
  border: 1px solid var(--bbz-border);
  border-radius: 0 var(--bbz-radius) var(--bbz-radius) var(--bbz-radius);
  padding: 0.6rem;
}
.comms__h {
  margin: 0.75rem 0 0.25rem;
  font-size: 0.85rem;
}
.comms__error {
  color: var(--bbz-danger-text);
  font-size: 0.85rem;
  margin: 0;
}
.comms__muted {
  color: var(--bbz-text-muted);
  font-size: 0.85rem;
  list-style: none;
}
.comms__lines {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;
}
.comms__line {
  font-size: 0.7rem;
  padding: 0.1rem 0.35rem;
  border-radius: var(--bbz-radius-sm);
  background: var(--bbz-surface-alt);
  color: var(--bbz-text-muted);
}
.comms__line--down {
  color: var(--bbz-danger-text);
  text-decoration: line-through;
}

/* dial pad */
.tp {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}
.tp__srlabel {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
}
.tp__display {
  padding: 0.4rem;
  font-size: 1.1rem;
  text-align: center;
  border: 1px solid var(--bbz-border);
  border-radius: var(--bbz-radius);
  background: var(--bbz-bg);
  color: var(--bbz-text);
}
.tp__pad {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 0.3rem;
}
.tp__key {
  padding: 0.5rem;
  font-size: 1rem;
  border: 1px solid var(--bbz-border);
  border-radius: var(--bbz-radius);
  background: var(--bbz-surface);
  color: var(--bbz-text);
  cursor: pointer;
}
.tp__key:focus-visible {
  outline: var(--bbz-focus-width) solid var(--bbz-focus-color);
}
.tp__row {
  display: flex;
  gap: 0.3rem;
}
.tp__row button {
  padding: 0.45rem 0.6rem;
  border: 1px solid var(--bbz-border);
  border-radius: var(--bbz-radius);
  background: var(--bbz-surface);
  color: var(--bbz-text);
  cursor: pointer;
}
.tp__call {
  flex: 1;
  background: var(--bbz-call) !important;
  color: var(--bbz-on-call) !important;
  font-weight: 600;
}
.tp__call:disabled {
  opacity: 0.5;
}
.tp__quickdial {
  padding: 0.45rem 0.6rem;
  border: 1px solid var(--bbz-border);
  border-radius: var(--bbz-radius);
  background: var(--bbz-surface);
  color: var(--bbz-text);
  cursor: pointer;
}

/* waiting queue */
.wq {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}
.wq__item {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.35rem 0.5rem;
  border-radius: var(--bbz-radius);
  border-left: 4px solid var(--bbz-border);
  background: var(--bbz-surface-alt);
}
.wq__item--high {
  border-left-color: var(--bbz-prio-high);
  animation: wq-pulse 1.4s ease-in-out infinite;
}
.wq__item--medium {
  border-left-color: var(--bbz-prio-medium);
}
.wq__item--low {
  border-left-color: var(--bbz-prio-low);
}
.wq__item--still {
  animation: none !important;
}
@keyframes wq-pulse {
  0%,
  100% {
    background: var(--bbz-surface-alt);
  }
  50% {
    background: color-mix(in srgb, var(--bbz-prio-high) 22%, var(--bbz-surface-alt));
  }
}
.wq__who {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.wq__prio {
  font-size: 0.72rem;
  text-transform: uppercase;
  color: var(--bbz-text-muted);
}
.wq__answer {
  margin-left: auto;
  padding: 0.25rem 0.6rem;
  border: 1px solid var(--bbz-accent);
  border-radius: var(--bbz-radius);
  background: var(--bbz-accent);
  color: #fff;
  cursor: pointer;
}

/* active call */
.ac {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
}
.ac__who {
  flex: 1;
  min-width: 0;
  font-size: 1.1rem;
  font-weight: 600;
}
.ac__duration {
  font-variant-numeric: tabular-nums;
  font-size: 0.85rem;
  color: var(--bbz-text-muted);
}
.ac__state {
  font-size: 0.8rem;
  color: var(--bbz-text-muted);
}
.ac__docreq {
  margin: 0.5rem 0;
  padding: 0.4rem 0.6rem;
  border-radius: var(--bbz-radius);
  background: color-mix(in srgb, var(--bbz-prio-medium) 18%, var(--bbz-surface));
  color: var(--bbz-warn-text);
  font-size: 0.85rem;
}
.ac__controls {
  display: flex;
  gap: 0.3rem;
  margin: 0.6rem 0;
}
.ac__controls button,
.ac__transfer button,
.ac__doc button {
  padding: 0.35rem 0.7rem;
  border: 1px solid var(--bbz-border);
  border-radius: var(--bbz-radius);
  background: var(--bbz-surface);
  color: var(--bbz-text);
  cursor: pointer;
}
.ac__hangup {
  background: var(--bbz-prio-high) !important;
  color: #fff !important;
  border-color: var(--bbz-prio-high) !important;
}
.ac__transfer {
  display: flex;
  align-items: end;
  gap: 0.3rem;
  margin-bottom: 0.6rem;
}
.ac__transfer input {
  flex: 1;
  padding: 0.3rem;
  border: 1px solid var(--bbz-border);
  border-radius: var(--bbz-radius);
  background: var(--bbz-bg);
  color: var(--bbz-text);
}
.ac__doc fieldset {
  border: 1px solid var(--bbz-border);
  border-radius: var(--bbz-radius);
  margin: 0 0 0.5rem;
  padding: 0.4rem 0.6rem;
}
.ac__doc legend {
  font-size: 0.78rem;
  font-weight: 600;
}
.ac__cat {
  display: block;
  font-size: 0.85rem;
  padding: 0.1rem 0;
}
.ac__doc textarea {
  width: 100%;
  padding: 0.3rem;
  border: 1px solid var(--bbz-border);
  border-radius: var(--bbz-radius);
  background: var(--bbz-bg);
  color: var(--bbz-text);
}
.ac__doc label {
  display: block;
  font-size: 0.8rem;
  margin: 0.3rem 0 0.15rem;
}

/* mini phonebook + history */
.mini,
.hist {
  list-style: none;
  margin: 0.4rem 0 0;
  padding: 0;
}
.mini__row {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  width: 100%;
  padding: 0.35rem 0.4rem;
  border: 0;
  border-bottom: 1px solid var(--bbz-border);
  background: none;
  color: var(--bbz-text);
  text-align: left;
  cursor: pointer;
}
.mini__row:disabled {
  opacity: 0.5;
  cursor: default;
}
.mini__prio {
  width: 0.6rem;
  height: 0.6rem;
  border-radius: 50%;
  flex: none;
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
.mini__name {
  font-weight: 600;
}
.mini__num {
  margin-left: auto;
  color: var(--bbz-text-muted);
  font-variant-numeric: tabular-nums;
}
.hist__item {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.3rem 0.2rem;
  border-bottom: 1px solid var(--bbz-border);
  font-size: 0.85rem;
}
.hist__dir {
  color: var(--bbz-text-muted);
}
.hist__who {
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.hist__cat {
  color: var(--bbz-text-muted);
  font-size: 0.78rem;
}
.hist__time {
  margin-left: auto;
  color: var(--bbz-text-muted);
  font-variant-numeric: tabular-nums;
}
</style>
