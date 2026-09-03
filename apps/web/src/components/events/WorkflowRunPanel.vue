<script setup lang="ts">
/**
 * Actions panel — workflow execution view (E07-09 / #109). Shows the bound
 * template + version, completed task steps and decisions. The graphical editor
 * is #129; this is the read/act runtime view.
 */
import { onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { eventsApi, type WorkflowInstance } from '@/lib/events';

const props = defineProps<{ eventId: string }>();
const { t, d } = useI18n();

const wf = ref<WorkflowInstance | null>(null);
const loaded = ref(false);

async function load(): Promise<void> {
  loaded.value = false;
  try {
    wf.value = await eventsApi.workflow(props.eventId);
  } catch {
    wf.value = null;
  } finally {
    loaded.value = true;
  }
}

onMounted(load);
watch(() => props.eventId, load);
</script>

<template>
  <section aria-labelledby="wf-h">
    <h2 id="wf-h">
      {{ t('workflow.title') }}
    </h2>

    <p
      v-if="loaded && !wf"
      class="wf__none"
    >
      {{ t('workflow.none') }}
    </p>

    <template v-else-if="wf">
      <p class="wf__meta">
        <span>{{ wf.template_name ?? wf.template_key ?? '—' }}</span>
        <span v-if="wf.template_version">· v{{ wf.template_version }}</span>
        <span class="wf__status">{{ t('workflow.status.' + wf.status) }}</span>
      </p>

      <ol class="wf__steps">
        <li
          v-for="s in wf.task_results"
          :key="s.node_key"
        >
          <span class="wf__done">✓</span>
          <span>{{ s.node_key }}</span>
          <time
            v-if="s.completed_at"
            :datetime="s.completed_at"
          >{{ d(new Date(s.completed_at), 'short') }}</time>
        </li>
        <li
          v-for="dec in wf.decisions"
          :key="'d-' + dec.connector_node_key"
          class="wf__decision"
        >
          <span class="wf__done">◈</span>
          <span>{{ dec.connector_node_key }} → {{ dec.chosen_branches.join(', ') }}</span>
          <span
            v-if="dec.auto"
            class="wf__auto"
          >{{ t('workflow.auto') }}</span>
        </li>
        <li
          v-if="wf.task_results.length === 0 && wf.decisions.length === 0"
          class="wf__none"
        >
          {{ t('workflow.nothingYet') }}
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
.wf__none {
  color: var(--bbz-text-muted);
  font-size: 0.85rem;
}
.wf__meta {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  align-items: baseline;
  font-size: 0.85rem;
  margin: 0 0 0.5rem;
}
.wf__status {
  color: var(--bbz-text-muted);
}
.wf__steps {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}
.wf__steps li {
  display: flex;
  align-items: baseline;
  gap: 0.5rem;
  font-size: 0.85rem;
}
.wf__done {
  color: var(--bbz-success-text);
}
.wf__decision .wf__done {
  color: var(--bbz-prio-medium);
}
.wf__auto {
  color: var(--bbz-text-muted);
  font-size: 0.78rem;
}
.wf__steps time {
  color: var(--bbz-text-muted);
  font-size: 0.78rem;
  margin-left: auto;
}
</style>
