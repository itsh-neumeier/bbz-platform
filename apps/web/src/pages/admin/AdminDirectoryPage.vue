<script setup lang="ts">
/**
 * Directory (LDAP/AD) administration (#723, part of #718).
 * - the non-secret connection fields via the settings store (#720, group
 *   `directory`); the bind password stays with the secret store (ADR-0019).
 * - "Verbindung testen" → `POST /admin/directory/test` (structured result).
 * - group→role mappings (`/auth/group-mappings`, provider `ldap_ad`).
 * - trigger a directory sync + show the last run (`/auth/directory-sync`).
 */
import { computed, onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { ApiError } from '@/lib/apiClient';
import { adminApi, type AdminSetting, type SettingValue } from '@/lib/admin';
import {
  directoryApi,
  groupMappingsApi,
  type DirectoryTestResult,
  type GroupMapping,
  type SyncReport,
  type SyncState,
} from '@/lib/directory';
import { rolesApi, type Role } from '@/lib/users';
import { useSessionStore } from '@/stores/session';

const { t } = useI18n();
const session = useSessionStore();
const canSettings = computed(() => session.can('system.settings.manage'));
const canRoles = computed(() => session.can('roles.manage'));
const canSync = computed(() => session.can('users.manage'));

const fields = ref<AdminSetting[]>([]);
const draft = ref<Record<string, string>>({});
const pwConfigured = ref<boolean | null>(null);
const error = ref('');
const savedHint = ref(false);
const busy = ref('');

const roles = ref<Role[]>([]);
const mappings = ref<GroupMapping[]>([]);
const newMap = ref({ external_group: '', role_key: '' });

const testResult = ref<DirectoryTestResult | null>(null);
const syncState = ref<SyncState | null>(null);
const syncReport = ref<SyncReport | null>(null);
const dryRun = ref(true);

const configured = computed(() => (draft.value['directory.ldap_url'] ?? '').trim().length > 0);
const dirty = computed(() =>
  fields.value.some((f) => (draft.value[f.key] ?? '') !== String(f.value ?? '')),
);

async function loadSettings(): Promise<void> {
  const groups = (await adminApi.settings()).groups;
  const g = groups.find((x) => x.group === 'directory');
  fields.value = (g?.items ?? []).filter((i) => !i.secret);
  draft.value = Object.fromEntries(fields.value.map((i) => [i.key, String(i.value ?? '')]));
  const pw = (g?.items ?? []).find((i) => i.secret);
  pwConfigured.value = pw?.configured ?? null;
}

async function load(): Promise<void> {
  error.value = '';
  try {
    await Promise.all([
      loadSettings(),
      rolesApi.list().then((r) => (roles.value = r)),
      groupMappingsApi.list('ldap_ad').then((m) => (mappings.value = m.mappings)),
      directoryApi.syncState().then((s) => (syncState.value = s)).catch(() => {}),
    ]);
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('admin.directory.loadError');
  }
}

async function run(key: string, fn: () => Promise<unknown>): Promise<void> {
  busy.value = key;
  error.value = '';
  try {
    await fn();
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('admin.directory.actionError');
  } finally {
    busy.value = '';
  }
}

async function saveSettings(): Promise<void> {
  savedHint.value = false;
  await run('save', async () => {
    const values: Record<string, SettingValue> = {};
    for (const f of fields.value) {
      const next = (draft.value[f.key] ?? '').trim();
      if (next !== String(f.value ?? '')) values[f.key] = next;
    }
    await adminApi.updateSettings('directory', values);
    await loadSettings();
    savedHint.value = true;
  });
}

const testConnection = () =>
  run('test', async () => {
    testResult.value = await directoryApi.test();
  });

const addMapping = () =>
  run('map', async () => {
    const m = await groupMappingsApi.create(
      'ldap_ad',
      newMap.value.external_group.trim(),
      newMap.value.role_key,
    );
    mappings.value = [...mappings.value, m];
    newMap.value = { external_group: '', role_key: '' };
  });

const removeMapping = (id: string) =>
  run('map', async () => {
    await groupMappingsApi.remove(id);
    mappings.value = mappings.value.filter((m) => m.id !== id);
  });

const runSync = () =>
  run('sync', async () => {
    syncReport.value = await directoryApi.runSync(dryRun.value);
    syncState.value = await directoryApi.syncState().catch(() => syncState.value);
  });

onMounted(load);
</script>

<template>
  <section class="dir">
    <p
      v-if="error"
      role="alert"
      class="dir__error"
    >
      {{ error }}
    </p>
    <p
      v-if="!configured"
      class="dir__banner"
      role="status"
    >
      {{ t('admin.directory.notConfigured') }}
    </p>

    <div class="card">
      <div class="card-head">
        <div>
          <div class="card-title">
            {{ t('admin.directory.connTitle') }}
          </div>
          <div class="card-subtitle">
            {{ t('admin.directory.connSubtitle') }}
          </div>
        </div>
        <button
          type="button"
          class="btn ghost sm"
          :disabled="busy === 'test' || !configured"
          @click="testConnection"
        >
          {{ busy === 'test' ? t('admin.directory.testing') : t('admin.directory.testBtn') }}
        </button>
      </div>
      <form
        class="card-body dir__form"
        @submit.prevent="saveSettings"
      >
        <div
          v-for="f in fields"
          :key="f.key"
          class="dir__field"
        >
          <label :for="'d-' + f.name">{{ f.label }}</label>
          <input
            :id="'d-' + f.name"
            v-model="draft[f.key]"
            class="input"
            type="text"
            :disabled="!canSettings"
          >
          <small class="muted">{{ f.help }}
            <span
              class="tag"
              :class="f.source === 'database' ? 'blue' : 'gray'"
            >{{ t('admin.source.' + f.source) }}</span>
          </small>
        </div>
        <p class="dir__pw muted">
          {{ t('admin.directory.bindPw') }}
          <span
            class="tag"
            :class="pwConfigured ? 'green' : 'amber'"
          >{{ pwConfigured ? t('admin.directory.pwSet') : t('admin.directory.pwUnset') }}</span>
        </p>
        <button
          v-if="canSettings"
          type="submit"
          class="btn primary sm"
          :disabled="busy === 'save' || !dirty"
        >
          {{ t('admin.save') }}
        </button>
        <span
          v-if="savedHint"
          class="dir__ok"
        >{{ t('admin.directory.saved') }}</span>

        <div
          v-if="testResult"
          class="dir__test"
        >
          <span
            class="tag"
            :class="testResult.reachable ? 'green' : 'red'"
          >{{ t('admin.directory.reachable') }}</span>
          <span
            class="tag"
            :class="testResult.tls_ok ? 'green' : 'red'"
          >TLS</span>
          <span
            class="tag"
            :class="testResult.bind_ok ? 'green' : 'red'"
          >{{ t('admin.directory.bind') }}</span>
          <span
            v-if="testResult.sample_count !== null"
            class="tag gray"
          >{{ t('admin.directory.sample', { n: testResult.sample_count }) }}</span>
          <span
            v-if="testResult.error"
            class="dir__test-err"
          >{{ testResult.error }}</span>
        </div>
      </form>
    </div>

    <div class="card">
      <div class="card-head">
        <div class="card-title">
          {{ t('admin.directory.mapTitle') }}
        </div>
      </div>
      <div class="card-body">
        <table class="table">
          <thead>
            <tr>
              <th scope="col">
                {{ t('admin.directory.mapGroup') }}
              </th>
              <th scope="col">
                {{ t('admin.directory.mapRole') }}
              </th>
              <th scope="col" />
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="m in mappings"
              :key="m.id"
            >
              <td>{{ m.external_group }}</td>
              <td>{{ roles.find((r) => r.key === m.role_key)?.name ?? m.role_key }}</td>
              <td>
                <button
                  v-if="canRoles"
                  type="button"
                  class="btn ghost sm"
                  :disabled="busy === 'map'"
                  @click="removeMapping(m.id)"
                >
                  {{ t('admin.directory.mapRemove') }}
                </button>
              </td>
            </tr>
            <tr v-if="mappings.length === 0">
              <td
                colspan="3"
                class="muted"
              >
                {{ t('admin.directory.mapEmpty') }}
              </td>
            </tr>
          </tbody>
        </table>
        <form
          v-if="canRoles"
          class="dir__map-add"
          @submit.prevent="addMapping"
        >
          <input
            v-model="newMap.external_group"
            class="input"
            :placeholder="t('admin.directory.mapGroup')"
            :aria-label="t('admin.directory.mapGroup')"
            required
          >
          <select
            v-model="newMap.role_key"
            class="input"
            :aria-label="t('admin.directory.mapRole')"
            required
          >
            <option
              value=""
              disabled
            >
              {{ t('admin.directory.mapRole') }}
            </option>
            <option
              v-for="r in roles"
              :key="r.id"
              :value="r.key"
            >
              {{ r.name }}
            </option>
          </select>
          <button
            type="submit"
            class="btn primary sm"
            :disabled="busy === 'map'"
          >
            {{ t('admin.directory.mapAdd') }}
          </button>
        </form>
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <div>
          <div class="card-title">
            {{ t('admin.directory.syncTitle') }}
          </div>
          <div class="card-subtitle">
            {{ t('admin.directory.syncSubtitle') }}
          </div>
        </div>
      </div>
      <div class="card-body dir__sync">
        <p
          v-if="syncState"
          class="muted"
        >
          {{ t('admin.directory.lastRun', {
            at: syncState.last_run_at ?? '—',
            ok: syncState.last_error ? t('admin.directory.withError') : t('admin.directory.ok'),
          }) }}
        </p>
        <div
          v-if="canSync"
          class="dir__sync-run"
        >
          <label>
            <input
              v-model="dryRun"
              type="checkbox"
            >
            {{ t('admin.directory.dryRun') }}
          </label>
          <button
            type="button"
            class="btn primary sm"
            :disabled="busy === 'sync'"
            @click="runSync"
          >
            {{ busy === 'sync' ? t('admin.directory.syncing') : t('admin.directory.syncNow') }}
          </button>
        </div>
        <p
          v-if="syncReport"
          class="dir__report"
          :class="{ 'dir__report--bad': !syncReport.ok }"
        >
          {{ t('admin.directory.report', {
            scanned: syncReport.scanned,
            created: syncReport.created,
            deactivated: syncReport.deactivated,
          }) }}
          <span v-if="syncReport.dry_run">· {{ t('admin.directory.dryRunNote') }}</span>
          <span v-if="syncReport.error">· {{ syncReport.error }}</span>
        </p>
      </div>
    </div>
  </section>
</template>

<style scoped>
.dir {
  display: grid;
  gap: 0.9rem;
}
.dir__banner {
  padding: 0.6rem 0.8rem;
  border-radius: var(--bbz-radius);
  background: var(--bbz-warn-bg);
  color: var(--bbz-warn-text);
}
.dir__error {
  color: var(--bbz-danger-text);
}
.dir__form {
  display: grid;
  gap: 0.9rem;
  max-width: 40rem;
}
.dir__field {
  display: grid;
  gap: 0.3rem;
}
.dir__field label {
  font-weight: var(--bbz-weight-semibold);
  font-size: 0.9rem;
}
.dir__field .input {
  width: 100%;
}
.dir__field small,
.dir__pw {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
  font-size: 0.78rem;
}
.dir__ok,
.dir__saved {
  color: var(--bbz-success-text);
  font-size: 0.85rem;
}
.dir__test {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  flex-wrap: wrap;
}
.dir__test-err {
  color: var(--bbz-danger-text);
  font-size: 0.8rem;
}
.dir__map-add {
  display: flex;
  gap: 0.5rem;
  margin-top: 0.7rem;
  flex-wrap: wrap;
}
.dir__map-add .input {
  min-width: 12rem;
}
.dir__sync {
  display: grid;
  gap: 0.7rem;
}
.dir__sync-run {
  display: flex;
  align-items: center;
  gap: 0.8rem;
}
.dir__report {
  font-variant-numeric: tabular-nums;
}
.dir__report--bad {
  color: var(--bbz-danger-text);
}
</style>
