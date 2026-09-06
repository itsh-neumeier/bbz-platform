<script setup lang="ts">
/**
 * Monitor-/KVM-Routing-Dialog (E19-08 / #408, MASTER_PROMPT §9, V10 mockup
 * §13). The topbar monitor-layout button opens this. Inputs are assigned to
 * outputs **either** by dragging an input chip onto a monitor **or** — the
 * mouse-free alternative required by §26.14 — by picking the input in the
 * monitor's `<select>`. The lower-left workplace monitor is server-locked to
 * BBZ-OS (E19-03) and shown disabled. Standard-Layout reset + user profiles.
 * Native <dialog> (esc + focus trap), flex/grid on `.mrd__body` never on the
 * dialog element (see QuickDialOverlay.vue for why).
 */
import { computed, nextTick, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { ApiError } from '@/lib/apiClient';
import { useReducedMotion } from '@/composables/useReducedMotion';
import {
  monitorApi,
  type MonitorOutput,
  type MonitorProfile,
  type MonitorRoutes,
} from '@/lib/monitor';

const props = defineProps<{ open: boolean }>();
const emit = defineEmits<{ close: [] }>();
const { t } = useI18n();
const { reduced } = useReducedMotion();

const dialogEl = ref<HTMLDialogElement | null>(null);
const data = ref<MonitorRoutes | null>(null);
const profiles = ref<MonitorProfile[]>([]);
const error = ref('');
const busy = ref(false);
const newProfileName = ref('');
const selectedProfile = ref('');
const dragOverKey = ref('');

const gridOutputs = computed(() =>
  (data.value?.outputs ?? [])
    .filter((o) => !o.is_large_display)
    .slice()
    .sort((a, b) => a.grid_row! - b.grid_row! || a.grid_col! - b.grid_col!),
);
const largeDisplay = computed(() => data.value?.outputs.find((o) => o.is_large_display) ?? null);

function inputFor(outputKey: string): string {
  return data.value?.routes.find((r) => r.output_key === outputKey)?.input_key ?? '';
}
function inputLabel(key: string): string {
  return data.value?.inputs.find((i) => i.key === key)?.label ?? key;
}

async function load(): Promise<void> {
  error.value = '';
  try {
    data.value = await monitorApi.routes();
    profiles.value = (await monitorApi.profiles()).profiles;
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('monitor.loadError');
  }
}

async function route(outputKey: string, inputKey: string): Promise<void> {
  if (!inputKey || inputFor(outputKey) === inputKey) return;
  busy.value = true;
  error.value = '';
  try {
    data.value = await monitorApi.setRoutes({ [outputKey]: inputKey });
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('monitor.routeError');
    await load();
  } finally {
    busy.value = false;
  }
}

function onDrop(o: MonitorOutput, ev: DragEvent): void {
  dragOverKey.value = '';
  if (o.is_fixed) return;
  const inputKey = ev.dataTransfer?.getData('text/plain') ?? '';
  void route(o.key, inputKey);
}
function onDragOver(o: MonitorOutput, ev: DragEvent): void {
  if (o.is_fixed) return;
  ev.preventDefault();
  if (ev.dataTransfer) ev.dataTransfer.dropEffect = 'move';
  dragOverKey.value = o.key;
}

async function reset(): Promise<void> {
  busy.value = true;
  try {
    data.value = await monitorApi.resetStandard();
  } finally {
    busy.value = false;
  }
}

async function saveProfile(): Promise<void> {
  if (!newProfileName.value.trim() || !data.value) return;
  const layout = Object.fromEntries(data.value.routes.map((r) => [r.output_key, r.input_key]));
  await monitorApi.saveProfile(newProfileName.value.trim(), layout);
  newProfileName.value = '';
  profiles.value = (await monitorApi.profiles()).profiles;
}

async function applyProfile(): Promise<void> {
  if (!selectedProfile.value) return;
  busy.value = true;
  try {
    data.value = await monitorApi.applyProfile(selectedProfile.value);
  } finally {
    busy.value = false;
  }
}

watch(
  () => props.open,
  async (isOpen) => {
    if (!isOpen) {
      dialogEl.value?.close();
      return;
    }
    await load();
    await nextTick();
    dialogEl.value?.showModal?.();
    dialogEl.value?.querySelector<HTMLButtonElement>('.mrd__close')?.focus();
  },
  { immediate: true },
);
</script>

<template>
  <dialog
    ref="dialogEl"
    class="mrd"
    aria-labelledby="mrd-title"
    @close="emit('close')"
  >
    <div class="mrd__body">
      <header class="mrd__head">
        <div>
          <h2 id="mrd-title">
            {{ t('monitor.dialogTitle') }}
          </h2>
          <p class="mrd__sub">
            {{ t('monitor.dialogSubtitle') }}
          </p>
        </div>
        <button
          type="button"
          class="mrd__close"
          :aria-label="t('monitor.close')"
          @click="emit('close')"
        >
          ×
        </button>
      </header>

      <p
        v-if="error"
        class="mrd__error"
        role="alert"
      >
        {{ error }}
      </p>
      <p
        v-if="data && !data.provider_available"
        class="mrd__note"
      >
        {{ t('monitor.providerPending') }}
      </p>

      <template v-if="data">
        <div class="mrd__toolbar">
          <div class="mrd__palette-wrap">
            <span class="mrd__kicker">{{ t('monitor.inputsAvailable') }}</span>
            <!-- Drag & drop is a mouse-only enhancement; the keyboard-accessible
                 way to assign an input is each output's own <select> (§26.14),
                 so the drag source / drop targets legitimately carry no keyboard
                 handler of their own. -->
            <ul class="mrd__palette">
              <li
                v-for="i in data.inputs"
                :key="i.key"
              >
                <!-- eslint-disable-next-line vuejs-accessibility/no-static-element-interactions -->
                <span
                  class="mrd__source"
                  draggable="true"
                  :aria-label="t('monitor.inputAria', { input: i.label })"
                  @dragstart="(e: DragEvent) => e.dataTransfer?.setData('text/plain', i.key)"
                >
                  {{ i.label }}
                </span>
              </li>
            </ul>
          </div>
          <button
            type="button"
            class="mrd__std"
            :disabled="busy"
            @click="reset"
          >
            ↺ {{ t('monitor.standardLayout') }}
          </button>
        </div>

        <div class="mrd__area">
          <div>
            <span class="mrd__kicker">{{ t('monitor.gridLabel') }}</span>
            <div class="mrd__grid">
              <!-- eslint-disable-next-line vuejs-accessibility/no-static-element-interactions -->
              <fieldset
                v-for="o in gridOutputs"
                :key="o.key"
                class="mrd__output"
                :class="{
                  'mrd__output--fixed': o.is_fixed,
                  'mrd__output--dragover': dragOverKey === o.key && !reduced,
                }"
                @dragover="onDragOver(o, $event)"
                @dragleave="dragOverKey = ''"
                @drop.prevent="onDrop(o, $event)"
              >
                <legend>{{ o.label }}</legend>
                <span class="mrd__current">{{ inputLabel(inputFor(o.key)) }}</span>
                <select
                  :value="inputFor(o.key)"
                  :disabled="o.is_fixed || busy"
                  :aria-label="o.label"
                  @change="route(o.key, ($event.target as HTMLSelectElement).value)"
                >
                  <option
                    v-for="i in data.inputs"
                    :key="i.key"
                    :value="i.key"
                  >
                    {{ i.label }}
                  </option>
                </select>
                <span
                  v-if="o.is_fixed"
                  class="mrd__lock"
                >🔒 {{ t('monitor.fixed') }}</span>
              </fieldset>
            </div>
          </div>

          <div v-if="largeDisplay">
            <span class="mrd__kicker">{{ t('monitor.largeLabel') }}</span>
            <!-- eslint-disable-next-line vuejs-accessibility/no-static-element-interactions -->
            <fieldset
              class="mrd__output mrd__output--large"
              :class="{ 'mrd__output--dragover': dragOverKey === largeDisplay.key && !reduced }"
              @dragover="onDragOver(largeDisplay, $event)"
              @dragleave="dragOverKey = ''"
              @drop.prevent="onDrop(largeDisplay, $event)"
            >
              <legend>{{ largeDisplay.label }}</legend>
              <span class="mrd__current">{{ inputLabel(inputFor(largeDisplay.key)) }}</span>
              <select
                :value="inputFor(largeDisplay.key)"
                :disabled="busy"
                :aria-label="largeDisplay.label"
                @change="route(largeDisplay.key, ($event.target as HTMLSelectElement).value)"
              >
                <option
                  v-for="i in data.inputs"
                  :key="i.key"
                  :value="i.key"
                >
                  {{ i.label }}
                </option>
              </select>
            </fieldset>
          </div>
        </div>

        <p class="mrd__help">
          {{ t('monitor.dragHelp') }}
        </p>

        <div class="mrd__profiles">
          <form
            class="mrd__profile-save"
            @submit.prevent="saveProfile"
          >
            <label for="mrd-pname">{{ t('monitor.profileName') }}</label>
            <input
              id="mrd-pname"
              v-model="newProfileName"
              maxlength="120"
            >
            <button
              type="submit"
              :disabled="!newProfileName.trim()"
            >
              {{ t('monitor.saveProfile') }}
            </button>
          </form>

          <form
            v-if="profiles.length"
            class="mrd__profile-apply"
            @submit.prevent="applyProfile"
          >
            <label for="mrd-psel">{{ t('monitor.profile') }}</label>
            <select
              id="mrd-psel"
              v-model="selectedProfile"
            >
              <option value="">
                —
              </option>
              <option
                v-for="p in profiles"
                :key="p.id"
                :value="p.id"
              >
                {{ p.name }}
              </option>
            </select>
            <button
              type="submit"
              :disabled="!selectedProfile || busy"
            >
              {{ t('monitor.apply') }}
            </button>
          </form>
        </div>
      </template>
    </div>
  </dialog>
</template>

<style scoped>
.mrd {
  width: min(62rem, 94vw);
  max-height: 92vh;
  border: 1px solid var(--bbz-border);
  border-radius: var(--bbz-radius);
  padding: 1.2rem;
  background: var(--bbz-surface);
  color: var(--bbz-text);
}
.mrd::backdrop {
  background: rgb(0 0 0 / 45%);
}
/* flex/grid lives here, never on the <dialog> element (author `display` beats
   the UA `dialog:not([open]){display:none}` rule regardless of specificity). */
.mrd__body {
  display: flex;
  flex-direction: column;
  gap: 0.9rem;
  overflow: auto;
}
.mrd__head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
}
.mrd__head h2 {
  margin: 0;
  font-size: 1.05rem;
}
.mrd__sub {
  margin: 0.2rem 0 0;
  color: var(--bbz-text-muted);
  font-size: 0.8rem;
}
.mrd__close {
  border: 1px solid var(--bbz-border);
  border-radius: var(--bbz-radius);
  background: var(--bbz-bg);
  color: var(--bbz-text);
  font-size: 1rem;
  line-height: 1;
  padding: 0.2rem 0.5rem;
  cursor: pointer;
}
.mrd__kicker {
  display: block;
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--bbz-text-muted);
  margin-bottom: 0.35rem;
}
.mrd__toolbar {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  gap: 1rem;
  flex-wrap: wrap;
}
.mrd__palette {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  gap: 0.4rem;
  flex-wrap: wrap;
}
.mrd__source {
  display: inline-block;
  border: 1px solid var(--bbz-border);
  border-radius: var(--bbz-radius);
  background: var(--bbz-surface-alt);
  padding: 0.4rem 0.6rem;
  font-size: 0.78rem;
  font-weight: 600;
  cursor: grab;
  user-select: none;
}
.mrd__source:active {
  cursor: grabbing;
}
.mrd__std {
  padding: 0.4rem 0.8rem;
  border: 1px solid var(--bbz-border);
  border-radius: var(--bbz-radius);
  background: var(--bbz-bg);
  color: var(--bbz-text);
  cursor: pointer;
  white-space: nowrap;
}
.mrd__area {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 0.42fr);
  gap: 1.4rem;
  align-items: start;
}
.mrd__grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 0.7rem;
}
.mrd__output {
  border: 2px solid var(--bbz-border);
  border-radius: var(--bbz-radius);
  padding: 0.6rem;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  background: var(--bbz-bg);
  min-height: 7rem;
}
.mrd__output legend {
  font-size: 0.74rem;
  font-weight: 600;
  color: var(--bbz-text-muted);
  padding: 0 0.2rem;
}
.mrd__output--dragover {
  border-color: var(--bbz-accent);
  box-shadow: 0 0 0 4px color-mix(in srgb, var(--bbz-accent) 15%, transparent);
}
.mrd__output--fixed {
  background: var(--bbz-surface-alt);
}
.mrd__current {
  font-size: 1rem;
  font-weight: 700;
  text-align: center;
  margin: auto 0;
}
.mrd__output select {
  padding: 0.35rem;
  border: 1px solid var(--bbz-border);
  border-radius: var(--bbz-radius);
  background: var(--bbz-surface);
  color: var(--bbz-text);
  font-size: 0.8rem;
}
.mrd__output--large {
  min-height: 12rem;
}
.mrd__lock {
  font-size: 0.7rem;
  color: var(--bbz-text-muted);
  text-align: right;
}
.mrd__help {
  margin: 0;
  border: 1px solid var(--bbz-border);
  border-radius: var(--bbz-radius);
  padding: 0.5rem 0.7rem;
  color: var(--bbz-text-muted);
  font-size: 0.76rem;
}
.mrd__profiles {
  display: flex;
  flex-wrap: wrap;
  gap: 1.5rem;
}
.mrd__profile-save,
.mrd__profile-apply {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.85rem;
}
.mrd__profile-save input,
.mrd__profile-apply select {
  padding: 0.3rem;
  border: 1px solid var(--bbz-border);
  border-radius: var(--bbz-radius);
  background: var(--bbz-bg);
  color: var(--bbz-text);
}
.mrd__profiles button {
  padding: 0.35rem 0.7rem;
  border: 1px solid var(--bbz-border);
  border-radius: var(--bbz-radius);
  background: var(--bbz-bg);
  color: var(--bbz-text);
  cursor: pointer;
}
.mrd__profiles button:disabled,
.mrd__std:disabled {
  opacity: 0.6;
}
.mrd__error {
  margin: 0;
  color: var(--bbz-danger-text);
}
.mrd__note {
  margin: 0;
  color: var(--bbz-text-muted);
  font-size: 0.82rem;
}
@media (max-width: 60rem) {
  .mrd__area {
    grid-template-columns: 1fr;
  }
}
</style>
