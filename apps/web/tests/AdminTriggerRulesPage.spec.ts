import { beforeEach, describe, expect, it, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { createPinia, setActivePinia } from 'pinia';
import de from '@/i18n/de.json';
import AdminTriggerRulesPage from '@/pages/admin/AdminTriggerRulesPage.vue';
import { useSessionStore } from '@/stores/session';
import * as trig from '@/lib/triggers';

const RULES: trig.TriggerRule[] = [
  { id: 'r1', name: 'BMA → Ereignis', priority: 100, endpoint_id: null, lifecycle: 'published' },
];

beforeEach(() => {
  setActivePinia(createPinia());
  vi.restoreAllMocks();
  vi.spyOn(trig.triggerRulesApi, 'list').mockResolvedValue(RULES);
  vi.spyOn(trig.technicalEndpointsApi, 'list').mockResolvedValue([]);
});

async function factory(perms: string[]) {
  const s = useSessionStore();
  s.user = { id: 'me', display_name: 'Me', status: 'active' };
  s.permissions = perms;
  const i18n = createI18n({ legacy: false, locale: 'de', messages: { de } });
  const w = mount(AdminTriggerRulesPage, { global: { plugins: [i18n] } });
  await new Promise((r) => setTimeout(r, 0));
  await w.vm.$nextTick();
  return w;
}

describe('AdminTriggerRulesPage', () => {
  it('lists rules and opens the version detail', async () => {
    vi.spyOn(trig.triggerRulesApi, 'get').mockResolvedValue({
      ...RULES[0],
      versions: [
        {
          id: 'v1',
          rule_id: 'r1',
          version_no: 1,
          lifecycle: 'published',
          conditions: { any: [] },
          actions: [{ type: 'create_event' }],
          changelog: null,
        },
      ],
    });
    const w = await factory(['technical_endpoints.view']);
    expect(w.text()).toContain('BMA → Ereignis');
    await w.get('.tr__row').trigger('click');
    await new Promise((r) => setTimeout(r, 0));
    expect(w.get('.tr__ver').text()).toContain('Version 1');
    expect(w.get('.tr__json-view').text()).toContain('create_event');
  });

  it('runs a simulation', async () => {
    const sim = vi.spyOn(trig.triggerRulesApi, 'simulate').mockResolvedValue({
      signal_type: 'bma_alarm',
      executed: false,
      planned_action_count: 1,
      matched: [
        {
          rule_id: 'r1',
          rule_name: 'BMA → Ereignis',
          priority: 100,
          version_id: 'v1',
          version_no: 1,
          actions: [],
        },
      ],
    });
    const w = await factory(['technical_endpoints.view']);
    await w.get('.tr__sim textarea').setValue('{"type":"bma_alarm"}');
    await w.get('.tr__sim .btn.primary').trigger('click');
    await new Promise((r) => setTimeout(r, 0));
    expect(sim).toHaveBeenCalledWith({ type: 'bma_alarm' });
    expect(w.get('.tr__sim-result').text()).toContain('BMA → Ereignis');
  });
});
