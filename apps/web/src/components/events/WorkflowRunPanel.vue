<script setup lang="ts">
/**
 * Actions panel — workflow execution view (E07-09 / #109). Shows the bound
 * template + version, per-step state, and — for the steps a token is waiting on
 * — an "abschließen" button; for a pending XOR/OR split, a button per branch.
 * Mirrors the engine token state (`GET /events/{id}/workflow`). The graphical
 * editor is #129.
 */
import { computed, onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { ApiError, ConflictError } from '@/lib/apiClient';
import { eventsApi, type WorkflowInstance } from '@/lib/events';
import { useSessionStore } from '@/stores/session';

const props = defineProps<{ eventId: string }>();
const { t, d } = useI18n();
const session = useSessionStore();

const wf = ref<WorkflowInstance | null>(null);
const loaded = ref(false);
const busy = ref('');
const error = ref('');

const canExecute = computed(() => session.can('workflows.execute'));
const pct = computed(() =>
  wf.value && wf.value.progress.total > 0
    ? Math.round((wf.value.progress.done / wf.value.progress.total) * 100)
    : 0,
);

async function load(): Promise<void> {
  loaded.value = false;
  error.value = '';
  try {
    wf.value = await eventsApi.workflow(props.eventId);
  } catch (e) {
    wf.value = null;
    if (e instanceof ApiError && e.status !== 404) error.value = e.message;
  } finally {
    loaded.value = true;
  }
}

async function act(key: string, fn: () => Promise<WorkflowInstance>): Promise<void> {
  busy.value = key;
  error.value = '';
  try {
    wf.value = await fn();
  } catch (e) {
    error.value =
      e instanceof ConflictError
        ? t('workflow.stepConflict')
        : e instanceof ApiError
          ? e.message
          : t('workflow.actionError');
    await load();
  } finally {
    busy.value = '';
  }
}

const completeStep = (nodeKey: string) =>
  act('s-' + nodeKey, () => eventsApi.completeStep(props.eventId, nodeKey));

const decide = (connectorKey: string, branch: string) =>
  act('d-' + connectorKey, () => eventsApi.decide(props.eventId, connectorKey, [branch]));

onMounted(load);
watch(() => props.eventId, load);
</script>

<template>
  <section aria-labelledby="wf-h">
    <h2 id="wf-h">
      {{ t('workflow.title') }}
    </h2>

    <p
      v-if="error"
      role="alert"
      class="wf__error"
    >
      {{ error }}
    </p>
    <p
      v-if="loaded && !wf"
      class="wf__none"
    >
      {{ t('workflow.none') }}
    </p>

    <template v-if="wf">
      <p class="wf__meta">
        <span>{{ wf.template.key ?? '—' }}</span>
        <span>· v{{ wf.template.version_no }}</span>
        <span class="wf__status">{{ t('workflow.status.' + wf.status, wf.status) }}</span>
        <span class="wf__prog">{{ wf.progress.done }}/{{ wf.progress.total }}</span>
      </p>
      <div
        class="wf__bar"
        role="progressbar"
        :aria-valuenow="pct"
        aria-valuemin="0"
        aria-valuemax="100"
      >
        <span :style="{ width: pct + '%' }" />
      </div>

      <ol class="wf__steps">
        <li
          v-for="s in wf.steps"
          :key="s.node_key"
          class="wf__step"
          :class="'wf__step--' + s.state"
        >
          <span
            class="wf__mark"
            aria-hidden="true"
          >{{ s.state === 'done' ? '✓' : s.state === 'active' ? '▸' : '○' }}</span>
          <span class="wf__label">{{ s.label ?? s.node_key }}</span>
          <time
            v-if="s.completed_at"
            :datetime="s.completed_at"
          >{{ d(new Date(s.completed_at), 'short') }}</time>
          <button
            v-else-if="s.state === 'active' && canExecute"
            type="button"
            class="btn sm primary"
            :disabled="busy !== ''"
            @click="completeStep(s.node_key)"
          >
            {{ busy === 's-' + s.node_key ? t('workflow.completing') : t('workflow.completeStep') }}
          </button>
        </li>
      </ol>

      <div
        v-for="pd in wf.pending_decisions"
        :key="pd.connector_node_key"
        class="wf__decide"
      >
        <span class="wf__decide-label">{{ t('workflow.decide', { c: pd.connector_node_key }) }}</span>
        <button
          v-for="o in pd.options"
          :key="o.edge_key"
          type="button"
          class="btn sm"
          :disabled="busy !== '' || !canExecute"
          @click="decide(pd.connector_node_key, o.branch ?? o.to)"
        >
          {{ o.branch ?? o.to }}
        </button>
      </div>

      <ol
        v-if="wf.decisions.length"
        class="wf__steps wf__steps--decided"
      >
        <li
          v-for="dec in wf.decisions"
          :key="'d-' + dec.connector_node_key"
        >
          <span
            class="wf__mark"
            aria-hidden="true"
          >◈</span>
          <span>{{ dec.connector_node_key }} → {{ dec.chosen_branches.join(', ') }}</span>
          <span
            v-if="dec.auto"
            class="wf__auto"
          >{{ t('workflow.auto') }}</span>
        </li>
      </ol>
    </template>
  </section>
</template>

<style scoped>
h2 {
  font-size: 0.95rem;
  margin: 0 0 0.5rem;
}
.wf__none,
.wf__error {
  font-size: 0.85rem;
}
.wf__error {
  color: var(--bbz-danger-text);
}
.wf__none {
  color: var(--bbz-text-muted);
}
.wf__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  align-items: baseline;
  font-size: 0.85rem;
  margin: 0 0 0.35rem;
}
.wf__status {
  color: var(--bbz-text-muted);
}
.wf__prog {
  margin-left: auto;
  font-variant-numeric: tabular-nums;
  color: var(--bbz-text-muted);
}
.wf__bar {
  height: 4px;
  border-radius: 2px;
  background: var(--bbz-surface-alt);
  overflow: hidden;
  margin-bottom: 0.7rem;
}
.wf__bar span {
  display: block;
  height: 100%;
  background: var(--bbz-success);
  transition: width var(--bbz-transition);
}
.wf__steps {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
}
.wf__step {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.85rem;
}
.wf__mark {
  width: 1rem;
  text-align: center;
}
.wf__step--done .wf__mark {
  color: var(--bbz-success-text);
}
.wf__step--active .wf__mark {
  color: var(--bbz-info);
}
.wf__step--pending {
  color: var(--bbz-text-muted);
}
.wf__label {
  flex: 1;
}
.wf__step time {
  color: var(--bbz-text-muted);
  font-size: 0.78rem;
}
.wf__decide {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.4rem;
  margin: 0.6rem 0;
  padding: 0.5rem;
  border: var(--bbz-border-width) solid var(--bbz-border);
  border-radius: var(--bbz-radius);
  background: var(--bbz-surface-alt);
}
.wf__decide-label {
  font-size: 0.82rem;
}
.wf__steps--decided {
  margin-top: 0.6rem;
  opacity: 0.8;
}
.wf__steps--decided .wf__mark {
  color: var(--bbz-prio-medium);
}
.wf__auto {
  color: var(--bbz-text-muted);
  font-size: 0.78rem;
}
</style>
