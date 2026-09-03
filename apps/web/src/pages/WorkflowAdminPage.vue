<script setup lang="ts">
/**
 * Workflow-template admin / EPK editor (E07-19 / #129, MASTER_PROMPT §33).
 * A structural editor: pick a template, add a draft version, edit its nodes
 * (event / function / connector) and edges as forms, see an auto-laid-out
 * graph preview, validate against the publish gate (E05-06) and publish.
 * Drag-to-position on a canvas is a follow-up; the graph render here is
 * read-only and derived from edge depth.
 */
import { computed, nextTick, onMounted, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { ApiError } from '@/lib/apiClient';
import { useSessionStore } from '@/stores/session';
import {
  workflowsApi,
  emptyGraph,
  layoutColumns,
  CONNECTOR_KINDS,
  FUNCTION_KINDS,
  type WfGraph,
  type WfIssue,
  type WfNode,
  type WfTemplate,
  type WfTemplateDetail,
  type WfVersion,
} from '@/lib/workflows';

const { t } = useI18n();
const session = useSessionStore();
const canManage = computed(() => session.can('workflows.manage_templates'));

const templates = ref<WfTemplate[]>([]);
const detail = ref<WfTemplateDetail | null>(null);
const version = ref<WfVersion | null>(null);
const graph = ref<WfGraph>(emptyGraph());
const issues = ref<WfIssue[]>([]);
const error = ref('');
const info = ref('');
const busy = ref(false);

const editable = computed(() => version.value?.lifecycle === 'draft' && canManage.value);
const dirty = ref(false);
let syncing = false;
watch(
  graph,
  () => {
    if (!syncing) dirty.value = true;
  },
  { deep: true },
);

async function loadTemplates(): Promise<void> {
  try {
    templates.value = await workflowsApi.list();
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('wf.loadError');
  }
}

async function selectTemplate(id: string): Promise<void> {
  error.value = '';
  info.value = '';
  version.value = null;
  issues.value = [];
  try {
    detail.value = await workflowsApi.detail(id);
    const draft = detail.value.versions.find((v) => v.lifecycle === 'draft');
    if (draft) await selectVersion(draft.id);
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('wf.loadError');
  }
}

async function selectVersion(versionId: string): Promise<void> {
  error.value = '';
  issues.value = [];
  try {
    syncing = true;
    version.value = await workflowsApi.version(versionId);
    graph.value = normalise(version.value.definition);
    await nextTick();
    dirty.value = false;
    syncing = false;
  } catch (e) {
    syncing = false;
    error.value = e instanceof ApiError ? e.message : t('wf.loadError');
  }
}

function normalise(g: unknown): WfGraph {
  const gg = (g ?? {}) as Partial<WfGraph>;
  return {
    start: gg.start ?? 'start',
    nodes: Array.isArray(gg.nodes) ? (gg.nodes as WfNode[]) : [],
    edges: Array.isArray(gg.edges) ? gg.edges : [],
  };
}

// --- template + version lifecycle ------------------------------------
const newTpl = ref({ key: '', name: '' });
async function createTemplate(): Promise<void> {
  if (!newTpl.value.key.trim() || !newTpl.value.name.trim()) return;
  busy.value = true;
  try {
    const tpl = await workflowsApi.create(newTpl.value.key.trim(), newTpl.value.name.trim());
    newTpl.value = { key: '', name: '' };
    await loadTemplates();
    await selectTemplate(tpl.id);
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('wf.createError');
  } finally {
    busy.value = false;
  }
}

async function addDraft(): Promise<void> {
  if (!detail.value) return;
  busy.value = true;
  error.value = '';
  try {
    // a first version starts empty; a later one clones the graph on screen
    const base = detail.value.versions.length === 0 ? emptyGraph() : graph.value;
    const v = await workflowsApi.addVersion(detail.value.id, base, 'Entwurf');
    await selectTemplate(detail.value.id);
    await selectVersion(v.id);
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('wf.createError');
  } finally {
    busy.value = false;
  }
}

async function save(): Promise<void> {
  if (!version.value || !editable.value) return;
  busy.value = true;
  error.value = '';
  info.value = '';
  try {
    version.value = await workflowsApi.editVersion(version.value.id, graph.value);
    dirty.value = false;
    info.value = t('wf.saved');
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('wf.saveError');
  } finally {
    busy.value = false;
  }
}

async function validate(): Promise<void> {
  if (!version.value) return;
  if (dirty.value) await save();
  busy.value = true;
  try {
    const r = await workflowsApi.validate(version.value.id);
    issues.value = r.issues;
    info.value = r.valid ? t('wf.valid') : '';
    if (detail.value) await refreshDetail();
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('wf.saveError');
  } finally {
    busy.value = false;
  }
}

const publishNote = ref('');
async function publish(): Promise<void> {
  if (!version.value || !publishNote.value.trim()) return;
  busy.value = true;
  error.value = '';
  try {
    version.value = await workflowsApi.publish(version.value.id, publishNote.value.trim());
    publishNote.value = '';
    info.value = t('wf.published');
    await refreshDetail();
  } catch (e) {
    error.value = e instanceof ApiError ? e.message : t('wf.publishError');
  } finally {
    busy.value = false;
  }
}

async function refreshDetail(): Promise<void> {
  if (!detail.value) return;
  detail.value = await workflowsApi.detail(detail.value.id);
}

// --- node + edge editing -------------------------------------------
let seq = 0;
function uid(prefix: string): string {
  seq += 1;
  return `${prefix}${Date.now().toString(36).slice(-4)}${seq}`;
}

function addNode(type: WfNode['type']): void {
  const key = uid(type[0]);
  const n: WfNode = { key, type, label: '' };
  if (type === 'function') n.kind = 'manual';
  if (type === 'connector') {
    n.connector = 'and';
    n.direction = 'split';
  }
  graph.value.nodes.push(n);
}

function removeNode(key: string): void {
  graph.value.nodes = graph.value.nodes.filter((n) => n.key !== key);
  graph.value.edges = graph.value.edges.filter((e) => e.from !== key && e.to !== key);
  if (graph.value.start === key) graph.value.start = graph.value.nodes[0]?.key ?? 'start';
}

function addEdge(): void {
  const first = graph.value.nodes[0]?.key ?? '';
  graph.value.edges.push({ key: uid('e'), from: first, to: first });
}
function removeEdge(key: string): void {
  graph.value.edges = graph.value.edges.filter((e) => e.key !== key);
}

// --- preview -------------------------------------------------------
const COL_W = 150;
const ROW_H = 64;
const positions = computed(() => layoutColumns(graph.value));
const svgSize = computed(() => {
  let maxCol = 0;
  let maxRow = 0;
  for (const p of positions.value.values()) {
    maxCol = Math.max(maxCol, p.col);
    maxRow = Math.max(maxRow, p.row);
  }
  return { w: (maxCol + 1) * COL_W + 20, h: (maxRow + 1) * ROW_H + 20 };
});
function nodeXY(key: string): { x: number; y: number } {
  const p = positions.value.get(key) ?? { col: 0, row: 0 };
  return { x: p.col * COL_W + 20, y: p.row * ROW_H + 20 };
}
function nodeClass(n: WfNode): string {
  return `wfp__node wfp__node--${n.type}`;
}

onMounted(loadTemplates);
</script>

<template>
  <section class="wf">
    <h1>{{ t('wf.title') }}</h1>
    <p
      v-if="!canManage"
      class="wf__muted"
    >
      {{ t('wf.readonly') }}
    </p>

    <p
      v-if="error"
      class="wf__error"
      role="alert"
    >
      {{ error }}
    </p>
    <p
      v-if="info"
      class="wf__ok"
      role="status"
    >
      {{ info }}
    </p>

    <div class="wf__cols">
      <aside class="wf__list">
        <h2>{{ t('wf.templates') }}</h2>
        <ul>
          <li
            v-for="tpl in templates"
            :key="tpl.id"
          >
            <button
              type="button"
              :class="{ 'wf__sel': detail?.id === tpl.id }"
              @click="selectTemplate(tpl.id)"
            >
              {{ tpl.name }}
              <small>{{ tpl.key }}</small>
            </button>
          </li>
          <li v-if="!templates.length">
            <span class="wf__muted">{{ t('wf.noTemplates') }}</span>
          </li>
        </ul>

        <form
          v-if="canManage"
          class="wf__newtpl"
          @submit.prevent="createTemplate"
        >
          <label for="wf-key">{{ t('wf.key') }}</label>
          <input
            id="wf-key"
            v-model="newTpl.key"
            maxlength="64"
            pattern="[a-z0-9_.-]+"
          >
          <label for="wf-name">{{ t('wf.name') }}</label>
          <input
            id="wf-name"
            v-model="newTpl.name"
            maxlength="200"
          >
          <button
            type="submit"
            :disabled="busy || !newTpl.key.trim() || !newTpl.name.trim()"
          >
            {{ t('wf.newTemplate') }}
          </button>
        </form>
      </aside>

      <div
        v-if="detail"
        class="wf__editor"
      >
        <div class="wf__vers">
          <h2>{{ detail.name }}</h2>
          <ul>
            <li
              v-for="v in detail.versions"
              :key="v.id"
            >
              <button
                type="button"
                :class="{ 'wf__sel': version?.id === v.id }"
                @click="selectVersion(v.id)"
              >
                v{{ v.version_no }}
                <span
                  class="wf__lc"
                  :class="'wf__lc--' + v.lifecycle"
                >{{ t('wf.lc.' + v.lifecycle) }}</span>
              </button>
            </li>
          </ul>
          <button
            v-if="canManage"
            type="button"
            :disabled="busy"
            @click="addDraft"
          >
            {{ t('wf.newVersion') }}
          </button>
        </div>

        <div
          v-if="version"
          class="wf__graph"
        >
          <!-- preview -->
          <div
            class="wfp"
            role="img"
            :aria-label="t('wf.previewAlt')"
          >
            <svg
              :viewBox="`0 0 ${svgSize.w} ${svgSize.h}`"
              :width="svgSize.w"
              :height="svgSize.h"
            >
              <defs>
                <marker
                  id="wf-arrow"
                  viewBox="0 0 10 10"
                  refX="9"
                  refY="5"
                  markerWidth="7"
                  markerHeight="7"
                  orient="auto-start-reverse"
                >
                  <path
                    d="M0 0 L10 5 L0 10 z"
                    fill="currentColor"
                  />
                </marker>
              </defs>
              <line
                v-for="e in graph.edges"
                :key="e.key"
                :x1="nodeXY(e.from).x + 120"
                :y1="nodeXY(e.from).y + 18"
                :x2="nodeXY(e.to).x"
                :y2="nodeXY(e.to).y + 18"
                class="wfp__edge"
                marker-end="url(#wf-arrow)"
              />
              <g
                v-for="n in graph.nodes"
                :key="n.key"
              >
                <rect
                  :x="nodeXY(n.key).x"
                  :y="nodeXY(n.key).y"
                  width="120"
                  height="36"
                  rx="6"
                  :class="nodeClass(n)"
                />
                <text
                  :x="nodeXY(n.key).x + 60"
                  :y="nodeXY(n.key).y + 22"
                  text-anchor="middle"
                  class="wfp__label"
                >{{ n.label || n.key }}</text>
              </g>
            </svg>
          </div>

          <!-- issues -->
          <ul
            v-if="issues.length"
            class="wf__issues"
          >
            <li
              v-for="(is, i) in issues"
              :key="i"
            >
              <code v-if="is.node_key">{{ is.node_key }}</code>
              {{ is.message }}
            </li>
          </ul>

          <!-- node editor -->
          <fieldset :disabled="!editable">
            <legend>{{ t('wf.nodes') }}</legend>
            <table class="wf__tbl">
              <thead>
                <tr>
                  <th>{{ t('wf.nKey') }}</th>
                  <th>{{ t('wf.nType') }}</th>
                  <th>{{ t('wf.nLabel') }}</th>
                  <th>{{ t('wf.nDetail') }}</th>
                  <th><span class="wf__sr">{{ t('wf.actions') }}</span></th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="n in graph.nodes"
                  :key="n.key"
                >
                  <td>
                    <input
                      v-model="n.key"
                      :aria-label="t('wf.nKey')"
                      maxlength="64"
                    >
                  </td>
                  <td>{{ t('wf.type.' + n.type) }}</td>
                  <td>
                    <input
                      v-model="n.label"
                      :aria-label="t('wf.nLabel')"
                      maxlength="300"
                    >
                  </td>
                  <td>
                    <select
                      v-if="n.type === 'function'"
                      v-model="n.kind"
                      :aria-label="t('wf.nDetail')"
                    >
                      <option
                        v-for="k in FUNCTION_KINDS"
                        :key="k"
                        :value="k"
                      >
                        {{ t('wf.kind.' + k) }}
                      </option>
                    </select>
                    <span v-else-if="n.type === 'connector'">
                      <select
                        v-model="n.connector"
                        :aria-label="t('wf.nConnector')"
                      >
                        <option
                          v-for="c in CONNECTOR_KINDS"
                          :key="c"
                          :value="c"
                        >
                          c.toUpperCase()
                        </option>
                      </select>
                      <select
                        v-model="n.direction"
                        :aria-label="t('wf.nDirection')"
                      >
                        <option value="split">
                          {{ t('wf.split') }}
                        </option>
                        <option value="join">
                          {{ t('wf.join') }}
                        </option>
                      </select>
                    </span>
                    <span
                      v-else
                      class="wf__muted"
                    >—</span>
                  </td>
                  <td>
                    <button
                      type="button"
                      class="wf__x"
                      :aria-label="t('wf.remove')"
                      @click="removeNode(n.key)"
                    >
                      ✕
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
            <div class="wf__add">
              <button
                type="button"
                @click="addNode('event')"
              >
                + {{ t('wf.type.event') }}
              </button>
              <button
                type="button"
                @click="addNode('function')"
              >
                + {{ t('wf.type.function') }}
              </button>
              <button
                type="button"
                @click="addNode('connector')"
              >
                + {{ t('wf.type.connector') }}
              </button>
            </div>
          </fieldset>

          <!-- edge editor -->
          <fieldset :disabled="!editable">
            <legend>{{ t('wf.edges') }}</legend>
            <table class="wf__tbl">
              <thead>
                <tr>
                  <th>{{ t('wf.eFrom') }}</th>
                  <th>{{ t('wf.eTo') }}</th>
                  <th>{{ t('wf.eBranch') }}</th>
                  <th><span class="wf__sr">{{ t('wf.actions') }}</span></th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="e in graph.edges"
                  :key="e.key"
                >
                  <td>
                    <select
                      v-model="e.from"
                      :aria-label="t('wf.eFrom')"
                    >
                      <option
                        v-for="n in graph.nodes"
                        :key="n.key"
                        :value="n.key"
                      >
                        n.label || n.key
                      </option>
                    </select>
                  </td>
                  <td>
                    <select
                      v-model="e.to"
                      :aria-label="t('wf.eTo')"
                    >
                      <option
                        v-for="n in graph.nodes"
                        :key="n.key"
                        :value="n.key"
                      >
                        n.label || n.key
                      </option>
                    </select>
                  </td>
                  <td>
                    <input
                      v-model="e.branch"
                      :aria-label="t('wf.eBranch')"
                      maxlength="64"
                    >
                  </td>
                  <td>
                    <button
                      type="button"
                      class="wf__x"
                      :aria-label="t('wf.remove')"
                      @click="removeEdge(e.key)"
                    >
                      ✕
                    </button>
                  </td>
                </tr>
              </tbody>
            </table>
            <button
              type="button"
              class="wf__addedge"
              @click="addEdge"
            >
              + {{ t('wf.edge') }}
            </button>
          </fieldset>

          <fieldset :disabled="!editable">
            <legend>{{ t('wf.start') }}</legend>
            <select
              v-model="graph.start"
              :aria-label="t('wf.start')"
            >
              <option
                v-for="n in graph.nodes"
                :key="n.key"
                :value="n.key"
              >
                n.label || n.key
              </option>
            </select>
          </fieldset>

          <div
            v-if="canManage"
            class="wf__actions"
          >
            <button
              type="button"
              :disabled="busy || !editable || !dirty"
              @click="save"
            >
              {{ t('wf.save') }}
            </button>
            <button
              type="button"
              :disabled="busy || version.lifecycle === 'published'"
              @click="validate"
            >
              {{ t('wf.validate') }}
            </button>
            <form
              v-if="version.lifecycle === 'validated'"
              class="wf__pub"
              @submit.prevent="publish"
            >
              <label for="wf-pub">{{ t('wf.changelog') }}</label>
              <input
                id="wf-pub"
                v-model="publishNote"
                maxlength="4000"
              >
              <button
                type="submit"
                :disabled="busy || !publishNote.trim()"
              >
                {{ t('wf.publish') }}
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  </section>
</template>

<style scoped>
.wf h1 {
  margin: 0 0 0.5rem;
  font-size: 1.25rem;
}
.wf__cols {
  display: grid;
  grid-template-columns: 15rem 1fr;
  gap: 1.25rem;
  align-items: start;
}
@media (max-width: 60rem) {
  .wf__cols {
    grid-template-columns: 1fr;
  }
}
.wf__list ul,
.wf__vers ul {
  list-style: none;
  margin: 0 0 0.75rem;
  padding: 0;
}
.wf__list button,
.wf__vers button {
  display: block;
  width: 100%;
  text-align: left;
  padding: 0.4rem 0.6rem;
  border: 1px solid var(--bbz-border);
  border-radius: 4px;
  background: var(--bbz-surface);
  color: var(--bbz-text);
  cursor: pointer;
  margin-bottom: 0.2rem;
}
.wf__list button small {
  display: block;
  color: var(--bbz-text-muted);
  font-size: 0.75rem;
}
.wf__sel {
  outline: 2px solid var(--bbz-accent);
  font-weight: 600;
}
.wf__newtpl {
  display: grid;
  gap: 0.25rem;
  border-top: 1px solid var(--bbz-border);
  padding-top: 0.6rem;
}
.wf__newtpl input,
.wf__pub input {
  padding: 0.3rem;
  border: 1px solid var(--bbz-border);
  border-radius: 4px;
  background: var(--bbz-bg);
  color: var(--bbz-text);
}
.wf__newtpl label,
.wf__pub label {
  font-size: 0.78rem;
}
.wf__lc {
  font-size: 0.68rem;
  text-transform: uppercase;
  padding: 0.05rem 0.3rem;
  border-radius: 3px;
  background: var(--bbz-surface-alt);
  color: var(--bbz-text-muted);
  margin-left: 0.35rem;
}
.wf__lc--published {
  background: color-mix(in srgb, var(--bbz-prio-low) 25%, var(--bbz-surface));
  color: var(--bbz-text);
}
.wf__lc--validated {
  background: color-mix(in srgb, var(--bbz-accent) 25%, var(--bbz-surface));
}
.wfp {
  overflow-x: auto;
  border: 1px solid var(--bbz-border);
  border-radius: 6px;
  background: var(--bbz-surface);
  padding: 0.5rem;
  margin-bottom: 0.75rem;
  color: var(--bbz-text-muted);
}
.wfp__edge {
  stroke: var(--bbz-text-muted);
  stroke-width: 1.5;
}
.wfp__node {
  stroke: var(--bbz-border);
  fill: var(--bbz-surface-alt);
}
.wfp__node--event {
  fill: color-mix(in srgb, var(--bbz-prio-low) 18%, var(--bbz-surface));
}
.wfp__node--connector {
  fill: color-mix(in srgb, var(--bbz-prio-medium) 20%, var(--bbz-surface));
}
.wfp__label {
  fill: var(--bbz-text);
  font-size: 11px;
}
.wf__issues {
  margin: 0 0 0.75rem;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--bbz-warn-text);
  border-radius: 6px;
  font-size: 0.85rem;
}
.wf__issues code {
  background: var(--bbz-surface-alt);
  padding: 0 0.25rem;
  border-radius: 3px;
}
.wf__editor fieldset {
  border: 1px solid var(--bbz-border);
  border-radius: 6px;
  margin: 0 0 0.75rem;
  padding: 0.6rem 0.8rem;
}
.wf__editor legend {
  font-weight: 600;
  font-size: 0.85rem;
  padding: 0 0.3rem;
}
.wf__tbl {
  width: 100%;
  border-collapse: collapse;
  font-size: 0.85rem;
}
.wf__tbl th {
  text-align: left;
  font-size: 0.72rem;
  color: var(--bbz-text-muted);
  padding: 0.2rem 0.3rem;
}
.wf__tbl td {
  padding: 0.15rem 0.3rem;
}
.wf__tbl input,
.wf__tbl select {
  width: 100%;
  padding: 0.25rem;
  border: 1px solid var(--bbz-border);
  border-radius: 3px;
  background: var(--bbz-bg);
  color: var(--bbz-text);
}
.wf__x {
  border: 0;
  background: none;
  color: var(--bbz-danger-text);
  cursor: pointer;
}
.wf__add,
.wf__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
  margin-top: 0.5rem;
}
.wf__add button,
.wf__addedge,
.wf__actions button {
  padding: 0.35rem 0.7rem;
  border: 1px solid var(--bbz-border);
  border-radius: 4px;
  background: var(--bbz-bg);
  color: var(--bbz-text);
  cursor: pointer;
}
.wf__addedge {
  margin-top: 0.5rem;
}
.wf__pub {
  display: flex;
  align-items: end;
  gap: 0.4rem;
}
.wf__actions {
  align-items: end;
}
.wf__error {
  color: var(--bbz-danger-text);
}
.wf__ok {
  color: var(--bbz-success-text);
}
.wf__muted {
  color: var(--bbz-text-muted);
}
.wf__sr {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
}
</style>
