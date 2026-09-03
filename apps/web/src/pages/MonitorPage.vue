<script setup lang="ts">
/**
 * Monitor / KVM routing (E19-08 / #408, MASTER_PROMPT §9). The 3×2 workplace
 * grid + the large display; each output picks its input via a `<select>` (the
 * keyboard-accessible alternative to drag & drop — §26.14). `workplace4` is
 * server-locked to BBZ-OS (E19-03) and shown disabled. Standard layout +
 * user profiles.
 */
import { computed, onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { ApiError } from '@/lib/apiClient';
import { monitorApi, type MonitorOutput, type MonitorProfile, type MonitorRoutes } from '@/lib/monitor';

const { t } = useI18n();

const data = ref<MonitorRoutes | null>(null);
const profiles = ref<MonitorProfile[]>([]);
const error = ref('');
const busy = ref(false);
const newProfileName = ref('');
const selectedProfile = ref('');

const gridOutputs = computed(
  () =>
    (data.value?.outputs ?? [])
      .filter((o) => !o.is_large_display)
      .slice()
      .sort((a, b) => (a.grid_row! - b.grid_row!) || (a.grid_col! - b.grid_col!)),
);
const largeDisplay = computed(() => data.value?.outputs.find((o) => o.is_large_display) ?? null);

function inputFor(outputKey: string): string {
  return data.value?.routes.find((r) => r.output_key === outputKey)?.input_key ?? '';
}

async function load(): Promise<void> {
  try {
    data.value = await monitorApi.routes();
    profiles.value = (await monitorApi.profiles()).profiles;
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('monitor.loadError');
  }
}

async function route(outputKey: string, inputKey: string): Promise<void> {
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

function groupLabel(o: MonitorOutput): string {
  return o.label;
}

onMounted(load);
</script>

<template>
  <section class="mon">
    <h1>{{ t('monitor.title') }}</h1>

    <p
      v-if="error"
      class="mon__error"
      role="alert"
    >
      {{ error }}
    </p>
    <p
      v-if="data && !data.provider_available"
      class="mon__note"
    >
      {{ t('monitor.providerPending') }}
    </p>

    <div
      v-if="data"
      class="mon__grid"
    >
      <fieldset
        v-for="o in gridOutputs"
        :key="o.key"
        class="mon__cell"
        :class="{ 'mon__cell--fixed': o.is_fixed }"
      >
        <legend>{{ groupLabel(o) }}</legend>
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
          class="mon__lock"
        >{{ t('monitor.fixed') }}</span>
      </fieldset>
    </div>

    <fieldset
      v-if="largeDisplay && data"
      class="mon__cell mon__cell--large"
    >
      <legend>{{ largeDisplay.label }}</legend>
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

    <div
      v-if="data"
      class="mon__actions"
    >
      <button
        type="button"
        :disabled="busy"
        @click="reset"
      >
        {{ t('monitor.standardLayout') }}
      </button>

      <form
        class="mon__profile-save"
        @submit.prevent="saveProfile"
      >
        <label for="mon-pname">{{ t('monitor.profileName') }}</label>
        <input
          id="mon-pname"
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
        class="mon__profile-apply"
        @submit.prevent="applyProfile"
      >
        <label for="mon-psel">{{ t('monitor.profile') }}</label>
        <select
          id="mon-psel"
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
  </section>
</template>

<style scoped>
.mon h1 {
  margin: 0 0 0.75rem;
  font-size: 1.25rem;
}
.mon__grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(9rem, 1fr));
  gap: 0.75rem;
  max-width: 40rem;
}
.mon__cell {
  border: 1px solid var(--bbz-border);
  border-radius: 6px;
  padding: 0.6rem;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  background: var(--bbz-surface);
}
.mon__cell legend {
  font-size: 0.8rem;
  font-weight: 600;
  padding: 0 0.25rem;
}
.mon__cell select {
  padding: 0.35rem;
  border: 1px solid var(--bbz-border);
  border-radius: 4px;
  background: var(--bbz-bg);
  color: var(--bbz-text);
}
.mon__cell--fixed {
  background: var(--bbz-surface-alt);
}
.mon__cell--large {
  margin-top: 0.75rem;
  max-width: 40rem;
}
.mon__lock {
  font-size: 0.72rem;
  color: var(--bbz-text-muted);
}
.mon__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 1.25rem;
  align-items: flex-end;
  margin-top: 1.25rem;
}
.mon__actions button {
  padding: 0.4rem 0.8rem;
  border: 1px solid var(--bbz-border);
  border-radius: 4px;
  background: var(--bbz-bg);
  color: var(--bbz-text);
  cursor: pointer;
}
.mon__actions button:disabled {
  opacity: 0.6;
}
.mon__profile-save,
.mon__profile-apply {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  font-size: 0.85rem;
}
.mon__profile-save input,
.mon__profile-apply select {
  padding: 0.3rem;
  border: 1px solid var(--bbz-border);
  border-radius: 4px;
  background: var(--bbz-bg);
  color: var(--bbz-text);
}
.mon__error {
  color: var(--bbz-danger-text);
}
.mon__note {
  color: var(--bbz-text-muted);
  font-size: 0.85rem;
}
</style>
