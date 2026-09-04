import { beforeEach, describe, expect, it, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { createPinia, setActivePinia } from 'pinia';
import de from '@/i18n/de.json';
import WorkflowRunPanel from '@/components/events/WorkflowRunPanel.vue';
import { useSessionStore } from '@/stores/session';
import * as ev from '@/lib/events';

const inst = (over: Partial<ev.WorkflowInstance> = {}): ev.WorkflowInstance => ({
  instance_id: 'wi1',
  event_id: 'e1',
  status: 'running',
  started_at: '2026-01-01T08:00:00Z',
  ended_at: null,
  template: { key: 'bma', version_no: 2 },
  progress: { done: 1, total: 3 },
  steps: [
    { node_key: 'notify', kind: 'notify', label: 'Melden', state: 'done', completed_at: '2026-01-01T08:01:00Z' },
    { node_key: 'dispatch', kind: 'manual', label: 'Disponieren', state: 'active' },
    { node_key: 'close', kind: 'manual', label: 'Abschließen', state: 'pending' },
  ],
  pending_decisions: [],
  decisions: [],
  ...over,
});

beforeEach(() => {
  setActivePinia(createPinia());
  vi.restoreAllMocks();
});

async function factory(perms: string[], wf: ev.WorkflowInstance | 'none') {
  const s = useSessionStore();
  s.user = { id: 'u1', display_name: 'Op', status: 'active' };
  s.permissions = perms;
  vi.spyOn(ev.eventsApi, 'workflow').mockImplementation(async () => {
    if (wf === 'none') throw Object.assign(new Error('nf'), { status: 404 });
    return wf;
  });
  const i18n = createI18n({ legacy: false, locale: 'de', messages: { de } });
  const w = mount(WorkflowRunPanel, { props: { eventId: 'e1' }, global: { plugins: [i18n] } });
  await new Promise((r) => setTimeout(r, 0));
  await w.vm.$nextTick();
  return w;
}

describe('WorkflowRunPanel', () => {
  it('renders each step with its state and a progress readout', async () => {
    const w = await factory(['workflows.view'], inst());
    const steps = w.findAll('.wf__step');
    expect(steps).toHaveLength(3);
    expect(steps[0].classes()).toContain('wf__step--done');
    expect(steps[1].classes()).toContain('wf__step--active');
    expect(w.text()).toContain('1/3');
  });

  it('completes the active step with workflows.execute', async () => {
    const done = vi
      .spyOn(ev.eventsApi, 'completeStep')
      .mockResolvedValue(inst({ progress: { done: 2, total: 3 } }));
    const w = await factory(['workflows.view', 'workflows.execute'], inst());
    await w.get('.wf__step--active .btn.primary').trigger('click');
    expect(done).toHaveBeenCalledWith('e1', 'dispatch');
  });

  it('hides the complete button without workflows.execute', async () => {
    const w = await factory(['workflows.view'], inst());
    expect(w.find('.wf__step--active .btn').exists()).toBe(false);
  });

  it('offers a button per branch for a pending decision', async () => {
    const decide = vi.spyOn(ev.eventsApi, 'decide').mockResolvedValue(inst());
    const w = await factory(
      ['workflows.view', 'workflows.execute'],
      inst({
        pending_decisions: [
          {
            connector_node_key: 'xor1',
            connector_type: 'xor',
            options: [
              { edge_key: 'e-a', to: 'a', branch: 'ja', has_condition: false },
              { edge_key: 'e-b', to: 'b', branch: 'nein', has_condition: false },
            ],
          },
        ],
      }),
    );
    const btns = w.findAll('.wf__decide .btn');
    expect(btns.map((b) => b.text())).toEqual(['ja', 'nein']);
    await btns[1].trigger('click');
    expect(decide).toHaveBeenCalledWith('e1', 'xor1', ['nein']);
  });

  it('shows "no workflow" on a 404', async () => {
    const w = await factory(['workflows.view'], 'none');
    expect(w.text()).toContain('Kein Ablauf');
  });
});
