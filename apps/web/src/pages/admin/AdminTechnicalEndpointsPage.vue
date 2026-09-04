<script setup lang="ts">
/**
 * Technical endpoints (#725, MASTER_PROMPT §14) — technical contacts (BMA,
 * panic buttons, door stations, alarm dialers) kept separate from the human
 * phone book. Backend: Epic 15 `/technical-endpoints`.
 */
import { computed, onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { ApiError } from '@/lib/apiClient';
import {
  technicalEndpointsApi,
  ENDPOINT_TYPES,
  PRIORITIES,
  type TechnicalEndpoint,
} from '@/lib/triggers';
import { useSessionStore } from '@/stores/session';

const { t } = useI18n();
const session = useSessionStore();
const canManage = computed(() => session.can('technical_endpoints.manage'));

const rows = ref<TechnicalEndpoint[]>([]);
const error = ref('');
const busy = ref(false);
const showCreate = ref(false);
const draft = ref({ name: '', type: 'bma', site: '', default_priority: 'high' });

async function load(): Promise<void> {
  error.value = '';
  try {
    rows.value = await technicalEndpointsApi.list();
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('admin.endpoints.loadError');
  }
}

async function act(fn: () => Promise<unknown>): Promise<void> {
  busy.value = true;
  error.value = '';
  try {
    await fn();
    await load();
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('admin.endpoints.actionError');
  } finally {
    busy.value = false;
  }
}

const create = () =>
  act(async () => {
    await technicalEndpointsApi.create({
      name: draft.value.name.trim(),
      type: draft.value.type,
      site: draft.value.site.trim() || null,
      default_priority: draft.value.default_priority,
    });
    showCreate.value = false;
    draft.value = { name: '', type: 'bma', site: '', default_priority: 'high' };
  });

const toggleEnabled = (e: TechnicalEndpoint) =>
  act(() => technicalEndpointsApi.update(e.id, { enabled: !e.enabled }));

const remove = (e: TechnicalEndpoint) => {
  if (!confirm(t('admin.endpoints.confirmDelete', { name: e.name }))) return;
  return act(() => technicalEndpointsApi.remove(e.id));
};

onMounted(load);
</script>

<template>
  <div class="card">
    <div class="card-head">
      <div>
        <div class="card-title">
          {{ t('admin.endpoints.title') }}
        </div>
        <div class="card-subtitle">
          {{ t('admin.endpoints.subtitle') }}
        </div>
      </div>
      <button
        v-if="canManage"
        type="button"
        class="btn primary sm"
        @click="showCreate = !showCreate"
      >
        {{ t('admin.endpoints.new') }}
      </button>
    </div>
    <div class="card-body">
      <p
        v-if="error"
        role="alert"
        class="te__error"
      >
        {{ error }}
      </p>

      <form
        v-if="showCreate && canManage"
        class="te__create"
        @submit.prevent="create"
      >
        <label>{{ t('admin.endpoints.fName') }}
          <input
            v-model="draft.name"
            class="input"
            required
          >
        </label>
        <label>{{ t('admin.endpoints.fType') }}
          <select
            v-model="draft.type"
            class="input"
          >
            <option
              v-for="ty in ENDPOINT_TYPES"
              :key="ty"
              :value="ty"
            >
              {{ t('admin.endpoints.type.' + ty, ty) }}
            </option>
          </select>
        </label>
        <label>{{ t('admin.endpoints.fSite') }}
          <input
            v-model="draft.site"
            class="input"
          >
        </label>
        <label>{{ t('admin.endpoints.fPriority') }}
          <select
            v-model="draft.default_priority"
            class="input"
          >
            <option
              v-for="p in PRIORITIES"
              :key="p"
              :value="p"
            >
              {{ p }}
            </option>
          </select>
        </label>
        <button
          type="submit"
          class="btn primary sm"
          :disabled="busy || !draft.name.trim()"
        >
          {{ t('admin.endpoints.createBtn') }}
        </button>
      </form>

      <table class="table">
        <thead>
          <tr>
            <th scope="col">
              {{ t('admin.endpoints.colName') }}
            </th>
            <th scope="col">
              {{ t('admin.endpoints.colType') }}
            </th>
            <th scope="col">
              {{ t('admin.endpoints.colSite') }}
            </th>
            <th scope="col">
              {{ t('admin.endpoints.colPriority') }}
            </th>
            <th scope="col">
              {{ t('admin.endpoints.colEnabled') }}
            </th>
            <th scope="col" />
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="e in rows"
            :key="e.id"
          >
            <td>{{ e.name }}</td>
            <td>{{ t('admin.endpoints.type.' + e.type, e.type) }}</td>
            <td>{{ e.site ?? '—' }}</td>
            <td>{{ e.default_priority ?? '—' }}</td>
            <td>
              <button
                type="button"
                class="btn ghost sm"
                :disabled="!canManage || busy"
                @click="toggleEnabled(e)"
              >
                <span
                  class="tag"
                  :class="e.enabled ? 'green' : 'gray'"
                >{{ e.enabled ? t('admin.endpoints.on') : t('admin.endpoints.off') }}</span>
              </button>
            </td>
            <td>
              <button
                v-if="canManage"
                type="button"
                class="btn ghost sm"
                :disabled="busy"
                @click="remove(e)"
              >
                {{ t('admin.endpoints.delete') }}
              </button>
            </td>
          </tr>
          <tr v-if="rows.length === 0">
            <td
              colspan="6"
              class="muted"
            >
              {{ t('admin.endpoints.empty') }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.te__create {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
  align-items: end;
  padding: 0.8rem;
  margin-bottom: 0.8rem;
  border: var(--bbz-border-width) solid var(--bbz-border);
  border-radius: var(--bbz-radius);
  background: var(--bbz-surface-alt);
}
.te__create label {
  display: grid;
  gap: 0.2rem;
  font-size: 0.8rem;
}
.te__create .input {
  min-width: 10rem;
}
.te__error {
  color: var(--bbz-danger-text);
}
</style>
