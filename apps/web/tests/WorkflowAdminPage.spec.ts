import { beforeEach, describe, expect, it, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import { createI18n } from 'vue-i18n';
import de from '@/i18n/de.json';
import WorkflowAdminPage from '@/pages/WorkflowAdminPage.vue';
import { useSessionStore } from '@/stores/session';
import * as wf from '@/lib/workflows';

const TEMPLATES: wf.WfTemplate[] = [{ id: 't1', key: 'bma', name: 'BMA-Alarm' }];

const DETAIL: wf.WfTemplateDetail = {
  id: 't1',
  key: 'bma',
  name: 'BMA-Alarm',
  versions: [{ id: 'v1', version_no: 1, lifecycle: 'draft' }],
};

const VERSION: wf.WfVersion = {
  id: 'v1',
  template_id: 't1',
  version_no: 1,
  lifecycle: 'draft',
  changelog: null,
  definition: {
    start: 'e_start',
    nodes: [
      { key: 'e_start', type: 'event', label: 'Alarm' },
      { key: 'f_call', type: 'function', kind: 'manual', label: 'Anrufen' },
    ],
    edges: [{ key: 'e1', from: 'e_start', to: 'f_call' }],
  },
};

function mocks() {
  vi.spyOn(wf.workflowsApi, 'list').mockResolvedValue(TEMPLATES);
  vi.spyOn(wf.workflowsApi, 'detail').mockResolvedValue(DETAIL);
  vi.spyOn(wf.workflowsApi, 'version').mockResolvedValue(structuredClone(VERSION));
}

async function flush(w: { vm: { $nextTick: () => Promise<unknown> } }) {
  for (let i = 0; i < 4; i++) {
    await new Promise((r) => setTimeout(r, 0));
    await w.vm.$nextTick();
  }
}

async function factory(perms: string[]) {
  const i18n = createI18n({ legacy: false, locale: 'de', messages: { de } });
  const pinia = createPinia();
  setActivePinia(pinia);
  useSessionStore().permissions = perms;
  const w = mount(WorkflowAdminPage, { global: { plugins: [pinia, i18n] } });
  await flush(w);
  return w;
}

beforeEach(() => {
  vi.restoreAllMocks();
  mocks();
});

describe('WorkflowAdminPage', () => {
  it('lists templates', async () => {
    const w = await factory(['workflows.view']);
    expect(w.text()).toContain('BMA-Alarm');
  });

  it('opens a template and renders its draft graph', async () => {
    const w = await factory(['workflows.view', 'workflows.manage_templates']);
    await w.findAll('.wf__list button')[0].trigger('click');
    await flush(w);
    // two node rows in the node table
    expect(w.findAll('.wf__tbl').length).toBeGreaterThanOrEqual(2);
    expect(w.text()).toContain('Anrufen');
    // the SVG preview drew two node rects
    expect(w.findAll('.wfp__node')).toHaveLength(2);
  });

  it('adds and removes a node (and its edges)', async () => {
    const w = await factory(['workflows.view', 'workflows.manage_templates']);
    await w.findAll('.wf__list button')[0].trigger('click');
    await flush(w);

    const addFn = w.findAll('.wf__add button').find((b) => b.text().includes('Funktion'))!;
    await addFn.trigger('click');
    expect(w.findAll('.wfp__node')).toHaveLength(3);

    // remove the first node → its outgoing edge goes too
    await w.findAll('.wf__x')[0].trigger('click');
    expect(w.findAll('.wfp__node')).toHaveLength(2);
  });

  it('validates and surfaces issues', async () => {
    const validate = vi.spyOn(wf.workflowsApi, 'validate').mockResolvedValue({
      valid: false,
      lifecycle: 'draft',
      issues: [{ code: 'unreachable', message: 'Knoten nicht erreichbar', node_key: 'f_call' }],
    });
    vi.spyOn(wf.workflowsApi, 'editVersion').mockResolvedValue(structuredClone(VERSION));
    const w = await factory(['workflows.view', 'workflows.manage_templates']);
    await w.findAll('.wf__list button')[0].trigger('click');
    await flush(w);

    const btn = w.findAll('.wf__actions button').find((b) => b.text() === 'Validieren')!;
    await btn.trigger('click');
    await flush(w);
    expect(validate).toHaveBeenCalledWith('v1');
    expect(w.find('.wf__issues').text()).toContain('Knoten nicht erreichbar');
  });

  it('is read-only without workflows.manage_templates', async () => {
    const w = await factory(['workflows.view']);
    expect(w.text()).toContain('Nur Lesezugriff');
    expect(w.find('.wf__newtpl').exists()).toBe(false);
    await w.findAll('.wf__list button')[0].trigger('click');
    await flush(w);
    // the node/edge fieldsets are disabled
    const fs = w.findAll('.wf__editor fieldset');
    expect(fs.length).toBeGreaterThan(0);
    expect(fs.every((f) => f.attributes('disabled') !== undefined)).toBe(true);
  });
});
