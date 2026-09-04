<script setup lang="ts">
/**
 * Integrations (#724, part of #718). One card per domain (Telefonie · Video ·
 * Monitor · Wetter): the discoverable adapters, which one is active, a health
 * badge, and a mock hint. The selection is written through the settings store
 * (`PUT /admin/settings/integrations`, audited `SETTING_CHANGED`); a provider
 * instance is cached for the process lifetime, so a change takes effect on the
 * next restart — same as an environment change.
 */
import { computed, onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { ApiError } from '@/lib/apiClient';
import { adminApi, type DomainIntegration } from '@/lib/admin';
import { useSessionStore } from '@/stores/session';

const { t } = useI18n();
const session = useSessionStore();
const canConfigure = computed(() => session.can('integrations.configure'));

const domains = ref<DomainIntegration[]>([]);
const error = ref('');
const busy = ref('');
const savedDomain = ref('');

async function load(): Promise<void> {
  error.value = '';
  try {
    domains.value = (await adminApi.integrations()).domains;
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('admin.integrations.loadError');
  }
}

async function select(d: DomainIntegration, adapterId: string): Promise<void> {
  if (adapterId === d.active_id) return;
  busy.value = d.domain;
  error.value = '';
  savedDomain.value = '';
  try {
    await adminApi.updateSettings('integrations', { [d.setting_key]: adapterId });
    await load();
    savedDomain.value = d.domain;
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('admin.integrations.saveError');
  } finally {
    busy.value = '';
  }
}

const healthClass = (state: string | undefined) =>
  state === 'ok' ? 'green' : state === 'degraded' ? 'amber' : state ? 'red' : 'gray';

onMounted(load);
</script>

<template>
  <section class="ig">
    <p
      v-if="error"
      role="alert"
      class="ig__error"
    >
      {{ error }}
    </p>
    <p class="ig__note muted">
      {{ t('admin.integrations.restartNote') }}
    </p>

    <div class="ig__grid">
      <div
        v-for="d in domains"
        :key="d.domain"
        class="card"
      >
        <div class="card-head">
          <div>
            <div class="card-title">
              {{ t('admin.integrations.domain.' + d.domain, d.domain) }}
            </div>
            <div class="card-subtitle">
              <span
                class="tag"
                :class="healthClass(d.health?.state)"
              >{{ d.health ? t('admin.integrations.health.' + d.health.state, d.health.state) : t('admin.integrations.noHealth') }}</span>
              <span
                v-if="d.active_is_mock"
                class="tag amber"
              >{{ t('admin.integrations.mock') }}</span>
            </div>
          </div>
        </div>
        <div class="card-body ig__body">
          <label :for="'ig-' + d.domain">{{ t('admin.integrations.adapter') }}</label>
          <select
            :id="'ig-' + d.domain"
            class="input"
            :value="d.active_id"
            :disabled="!canConfigure || busy === d.domain"
            @change="select(d, ($event.target as HTMLSelectElement).value)"
          >
            <option
              v-for="a in d.available"
              :key="a.id"
              :value="a.id"
            >
              {{ a.name }}{{ a.mock ? ' · Mock' : '' }}
            </option>
            <option
              v-if="d.available.length === 0"
              :value="d.active_id"
            >
              {{ d.active_id || '—' }}
            </option>
          </select>
          <small class="muted">
            {{ t('admin.source.' + d.source) }}
            <span v-if="d.health"> · {{ d.health.summary }}</span>
          </small>
          <span
            v-if="savedDomain === d.domain"
            class="ig__ok"
          >{{ t('admin.integrations.saved') }}</span>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.ig {
  display: grid;
  gap: 0.9rem;
}
.ig__error {
  color: var(--bbz-danger-text);
}
.ig__grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(18rem, 1fr));
  gap: 0.9rem;
}
.ig__body {
  display: grid;
  gap: 0.35rem;
}
.ig__body label {
  font-weight: var(--bbz-weight-semibold);
  font-size: 0.85rem;
}
.card-subtitle {
  display: flex;
  gap: 0.35rem;
  flex-wrap: wrap;
}
.ig__ok {
  color: var(--bbz-success-text);
  font-size: 0.82rem;
}
</style>
