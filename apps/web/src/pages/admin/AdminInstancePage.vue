<script setup lang="ts">
/**
 * Instance settings (#721). The `instance` group of the runtime settings store
 * (ADR-0031) — the operator-facing BBZ name and short name. Writes through
 * `PUT /api/v1/admin/settings/instance`; on success it reloads `/meta` so the
 * new name shows immediately in the topbar, sidebar and document title.
 */
import { computed, onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { ApiError } from '@/lib/apiClient';
import { adminApi, type AdminSetting, type SettingValue } from '@/lib/admin';
import { useSessionStore } from '@/stores/session';

const { t } = useI18n();
const session = useSessionStore();

const items = ref<AdminSetting[]>([]);
const draft = ref<Record<string, string>>({});
const loading = ref(true);
const saving = ref(false);
const error = ref('');
const saved = ref(false);

const dirty = computed(() => items.value.some((i) => (draft.value[i.key] ?? '') !== String(i.value ?? '')));

async function load(): Promise<void> {
  loading.value = true;
  error.value = '';
  try {
    const groups = (await adminApi.settings()).groups;
    const g = groups.find((x) => x.group === 'instance');
    items.value = (g?.items ?? []).filter((i) => !i.secret);
    draft.value = Object.fromEntries(items.value.map((i) => [i.key, String(i.value ?? '')]));
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('admin.instance.loadError');
  } finally {
    loading.value = false;
  }
}

async function save(): Promise<void> {
  saving.value = true;
  error.value = '';
  saved.value = false;
  const values: Record<string, SettingValue> = {};
  for (const i of items.value) {
    const next = (draft.value[i.key] ?? '').trim();
    if (next !== String(i.value ?? '')) values[i.key] = next;
  }
  try {
    const r = await adminApi.updateSettings('instance', values);
    items.value = (r.groups.find((x) => x.group === 'instance')?.items ?? []).filter((i) => !i.secret);
    draft.value = Object.fromEntries(items.value.map((i) => [i.key, String(i.value ?? '')]));
    await session.loadMeta();
    saved.value = true;
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('admin.instance.saveError');
  } finally {
    saving.value = false;
  }
}

onMounted(load);
</script>

<template>
  <div class="card">
    <div class="card-head">
      <div>
        <div class="card-title">
          {{ t('admin.instance.title') }}
        </div>
        <div class="card-subtitle">
          {{ t('admin.instance.subtitle') }}
        </div>
      </div>
    </div>

    <form
      class="card-body ai-form"
      @submit.prevent="save"
    >
      <p
        v-if="error"
        role="alert"
        class="ai-error"
      >
        {{ error }}
      </p>
      <p
        v-else-if="saved"
        role="status"
        class="ai-ok"
      >
        {{ t('admin.instance.savedHint') }}
      </p>

      <p
        v-if="loading"
        class="muted"
      >
        {{ t('admin.loading') }}
      </p>

      <div
        v-for="i in items"
        :key="i.key"
        class="ai-field"
      >
        <label :for="'ai-' + i.name">{{ i.label }}</label>
        <input
          :id="'ai-' + i.name"
          v-model="draft[i.key]"
          class="input"
          type="text"
          :aria-describedby="'ai-h-' + i.name"
        >
        <small
          :id="'ai-h-' + i.name"
          class="ai-help"
        >
          {{ i.help }}
          <span
            class="tag"
            :class="i.source === 'database' ? 'blue' : 'gray'"
          >{{ t('admin.source.' + i.source) }}</span>
        </small>
      </div>

      <div
        v-if="!loading"
        class="ai-actions"
      >
        <button
          type="submit"
          class="btn primary"
          :disabled="saving || !dirty"
        >
          {{ saving ? t('admin.saving') : t('admin.save') }}
        </button>
      </div>
    </form>
  </div>
</template>

<style scoped>
.ai-form {
  display: grid;
  gap: 1rem;
  max-width: 34rem;
}
.ai-field {
  display: grid;
  gap: 0.3rem;
}
.ai-field label {
  font-weight: var(--bbz-weight-semibold);
  font-size: 0.9rem;
}
.ai-field .input {
  width: 100%;
}
.ai-help {
  color: var(--bbz-text-muted);
  font-size: 0.76rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}
.ai-actions {
  margin-top: 0.2rem;
}
.ai-error {
  color: var(--bbz-danger-text);
}
.ai-ok {
  color: var(--bbz-success-text);
}
</style>
