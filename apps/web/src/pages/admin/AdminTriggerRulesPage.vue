<script setup lang="ts">
/**
 * Telephone-number trigger rules (#725, MASTER_PROMPT §32, E15). List the rules
 * + their versions, validate / publish / retire a version, and run a
 * simulation against a synthetic signal. A structured condition/action editor
 * is a follow-up — draft conditions/actions are edited as JSON here.
 */
import { computed, onMounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import { ApiError } from '@/lib/apiClient';
import {
  triggerRulesApi,
  technicalEndpointsApi,
  type SimulationResult,
  type TechnicalEndpoint,
  type TriggerRule,
  type TriggerRuleDetail,
} from '@/lib/triggers';
import { useSessionStore } from '@/stores/session';

const { t } = useI18n();
const session = useSessionStore();
const canManage = computed(() => session.can('technical_endpoints.manage'));

const rules = ref<TriggerRule[]>([]);
const endpoints = ref<TechnicalEndpoint[]>([]);
const detail = ref<TriggerRuleDetail | null>(null);
const error = ref('');
const busy = ref('');

const showCreate = ref(false);
const draft = ref({ name: '', priority: 100, endpoint_id: '', conditions: '{}', actions: '[]' });

const simText = ref(
  JSON.stringify(
    {
      signal_type: 'BMA_ALARM_CALL',
      provider: 'telephony_mock',
      occurred_at: '2026-01-01T08:00:00Z',
      received_at: '2026-01-01T08:00:01Z',
      gateway_node: 'bbz-srv01',
      source: { ani: '+499115551234', dnis: '+49911999' },
    },
    null,
    2,
  ),
);
const simResult = ref<SimulationResult | null>(null);

const endpointName = (id: string | null) =>
  id ? (endpoints.value.find((e) => e.id === id)?.name ?? id) : '—';

async function load(): Promise<void> {
  error.value = '';
  try {
    [rules.value, endpoints.value] = await Promise.all([
      triggerRulesApi.list(),
      technicalEndpointsApi.list().catch(() => []),
    ]);
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('admin.triggers.loadError');
  }
}

async function act(key: string, fn: () => Promise<unknown>): Promise<void> {
  busy.value = key;
  error.value = '';
  try {
    await fn();
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('admin.triggers.actionError');
  } finally {
    busy.value = '';
  }
}

const open = (id: string) =>
  act('open', async () => {
    detail.value = await triggerRulesApi.get(id);
  });

const create = () =>
  act('create', async () => {
    const d = await triggerRulesApi.create({
      name: draft.value.name.trim(),
      priority: Number(draft.value.priority),
      endpoint_id: draft.value.endpoint_id || null,
      conditions: JSON.parse(draft.value.conditions || '{}'),
      actions: JSON.parse(draft.value.actions || '[]'),
    });
    rules.value = [...rules.value, d];
    detail.value = d;
    showCreate.value = false;
    draft.value = { name: '', priority: 100, endpoint_id: '', conditions: '{}', actions: '[]' };
  });

const validate = (versionId: string) =>
  act('v-' + versionId, async () => {
    const r = await triggerRulesApi.validate(versionId);
    if (!r.valid) error.value = t('admin.triggers.invalid', { issues: r.issues.join('; ') });
    if (detail.value) detail.value = await triggerRulesApi.get(detail.value.id);
  });

const publish = (versionId: string) =>
  act('v-' + versionId, async () => {
    await triggerRulesApi.publish(versionId);
    if (detail.value) detail.value = await triggerRulesApi.get(detail.value.id);
    await load();
  });

const retire = (versionId: string) =>
  act('v-' + versionId, async () => {
    await triggerRulesApi.retire(versionId);
    if (detail.value) detail.value = await triggerRulesApi.get(detail.value.id);
    await load();
  });

const simulate = () =>
  act('sim', async () => {
    simResult.value = await triggerRulesApi.simulate(JSON.parse(simText.value));
  });

onMounted(load);
</script>

<template>
  <section class="tr">
    <p
      v-if="error"
      role="alert"
      class="tr__error"
    >
      {{ error }}
    </p>

    <div class="detail-grid">
      <div class="card">
        <div class="card-head">
          <div class="card-title">
            {{ t('admin.triggers.listTitle') }}
          </div>
          <button
            v-if="canManage"
            type="button"
            class="btn primary sm"
            @click="showCreate = !showCreate"
          >
            {{ t('admin.triggers.new') }}
          </button>
        </div>
        <div class="card-body">
          <form
            v-if="showCreate && canManage"
            class="tr__create"
            @submit.prevent="create"
          >
            <label>{{ t('admin.triggers.fName') }}
              <input
                v-model="draft.name"
                class="input"
                required
              >
            </label>
            <label>{{ t('admin.triggers.fPriority') }}
              <input
                v-model.number="draft.priority"
                class="input"
                type="number"
                min="0"
              >
            </label>
            <label>{{ t('admin.triggers.fEndpoint') }}
              <select
                v-model="draft.endpoint_id"
                class="input"
              >
                <option value="">
                  {{ t('admin.triggers.noEndpoint') }}
                </option>
                <option
                  v-for="e in endpoints"
                  :key="e.id"
                  :value="e.id"
                >
                  {{ e.name }}
                </option>
              </select>
            </label>
            <label>{{ t('admin.triggers.fConditions') }}
              <textarea
                v-model="draft.conditions"
                class="input tr__json"
                rows="2"
              />
            </label>
            <label>{{ t('admin.triggers.fActions') }}
              <textarea
                v-model="draft.actions"
                class="input tr__json"
                rows="2"
              />
            </label>
            <button
              type="submit"
              class="btn primary sm"
              :disabled="busy === 'create' || !draft.name.trim()"
            >
              {{ t('admin.triggers.createBtn') }}
            </button>
          </form>

          <table class="table">
            <thead>
              <tr>
                <th scope="col">
                  {{ t('admin.triggers.colName') }}
                </th>
                <th scope="col">
                  {{ t('admin.triggers.colEndpoint') }}
                </th>
                <th scope="col">
                  {{ t('admin.triggers.colLifecycle') }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="r in rules"
                :key="r.id"
                class="tr__row"
                :class="{ 'tr__row--sel': detail?.id === r.id }"
                tabindex="0"
                @click="open(r.id)"
                @keydown.enter="open(r.id)"
              >
                <td>{{ r.name }}</td>
                <td>{{ endpointName(r.endpoint_id) }}</td>
                <td>
                  <span
                    class="tag"
                    :class="r.lifecycle === 'published' ? 'green' : 'gray'"
                  >{{ t('admin.triggers.lc.' + r.lifecycle, r.lifecycle) }}</span>
                </td>
              </tr>
              <tr v-if="rules.length === 0">
                <td
                  colspan="3"
                  class="muted"
                >
                  {{ t('admin.triggers.empty') }}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>

      <div class="card">
        <div class="card-head">
          <div class="card-title">
            {{ detail ? detail.name : t('admin.triggers.detailTitle') }}
          </div>
        </div>
        <div class="card-body tr__detail">
          <p
            v-if="!detail"
            class="muted"
          >
            {{ t('admin.triggers.selectPrompt') }}
          </p>
          <template v-else>
            <div
              v-for="v in detail.versions"
              :key="v.id"
              class="tr__ver"
            >
              <div class="tr__ver-head">
                <b>{{ t('admin.triggers.version', { n: v.version_no }) }}</b>
                <span
                  class="tag"
                  :class="v.lifecycle === 'published' ? 'green' : v.lifecycle === 'retired' ? 'gray' : 'amber'"
                >{{ t('admin.triggers.lc.' + v.lifecycle, v.lifecycle) }}</span>
                <span
                  v-if="canManage"
                  class="tr__ver-actions"
                >
                  <button
                    type="button"
                    class="btn ghost sm"
                    :disabled="busy === 'v-' + v.id"
                    @click="validate(v.id)"
                  >
                    {{ t('admin.triggers.validate') }}
                  </button>
                  <button
                    v-if="v.lifecycle === 'validated'"
                    type="button"
                    class="btn primary sm"
                    :disabled="busy === 'v-' + v.id"
                    @click="publish(v.id)"
                  >
                    {{ t('admin.triggers.publish') }}
                  </button>
                  <button
                    v-if="v.lifecycle === 'published'"
                    type="button"
                    class="btn danger sm"
                    :disabled="busy === 'v-' + v.id"
                    @click="retire(v.id)"
                  >
                    {{ t('admin.triggers.retire') }}
                  </button>
                </span>
              </div>
              <pre class="tr__json-view">{{ JSON.stringify({ conditions: v.conditions, actions: v.actions }, null, 2) }}</pre>
            </div>
          </template>
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-head">
        <div>
          <div class="card-title">
            {{ t('admin.triggers.simTitle') }}
          </div>
          <div class="card-subtitle">
            {{ t('admin.triggers.simSubtitle') }}
          </div>
        </div>
      </div>
      <div class="card-body tr__sim">
        <label class="tr__sim-label">
          <span class="sr-only">{{ t('admin.triggers.simSignal') }}</span>
          <textarea
            v-model="simText"
            class="input tr__json"
            rows="4"
            :aria-label="t('admin.triggers.simSignal')"
          />
        </label>
        <button
          type="button"
          class="btn primary sm"
          :disabled="busy === 'sim'"
          @click="simulate"
        >
          {{ t('admin.triggers.runSim') }}
        </button>
        <p
          v-if="simResult"
          class="tr__sim-result"
        >
          {{ t('admin.triggers.simResult', {
            type: simResult.signal_type,
            n: simResult.matched.length,
            actions: simResult.planned_action_count,
          }) }}
          <span v-if="simResult.matched.length">·
            {{ simResult.matched.map((m) => m.rule_name).join(', ') }}</span>
        </p>
      </div>
    </div>
  </section>
</template>

<style scoped>
.tr {
  display: grid;
  gap: 0.9rem;
}
.tr__error {
  color: var(--bbz-danger-text);
}
.tr__row {
  cursor: pointer;
}
.tr__row:hover {
  background: var(--bbz-surface-alt);
}
.tr__row:focus-visible {
  outline: var(--bbz-focus-width) solid var(--bbz-focus-color);
  outline-offset: -2px;
}
.tr__row--sel {
  background: var(--bbz-info-bg);
  box-shadow: inset 3px 0 0 var(--bbz-info);
}
.tr__create {
  display: grid;
  gap: 0.5rem;
  padding: 0.8rem;
  margin-bottom: 0.8rem;
  border: var(--bbz-border-width) solid var(--bbz-border);
  border-radius: var(--bbz-radius);
  background: var(--bbz-surface-alt);
}
.tr__create label {
  display: grid;
  gap: 0.2rem;
  font-size: 0.8rem;
}
.tr__json {
  font-family: var(--bbz-font-mono, monospace);
  font-size: 0.8rem;
}
.tr__detail {
  display: grid;
  gap: 0.8rem;
}
.tr__ver {
  border: var(--bbz-border-width) solid var(--bbz-border);
  border-radius: var(--bbz-radius);
  padding: 0.6rem;
}
.tr__ver-head {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}
.tr__ver-actions {
  display: flex;
  gap: 0.3rem;
  margin-left: auto;
}
.tr__json-view {
  margin: 0.5rem 0 0;
  padding: 0.5rem;
  background: var(--bbz-surface-alt);
  border-radius: var(--bbz-radius);
  font-size: 0.76rem;
  overflow-x: auto;
}
.tr__sim {
  display: grid;
  gap: 0.6rem;
  max-width: 40rem;
}
.tr__sim-result {
  font-variant-numeric: tabular-nums;
}
.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
}
</style>
