import { beforeEach, describe, expect, it, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { createPinia, setActivePinia } from 'pinia';
import de from '@/i18n/de.json';
import AdminTechnicalEndpointsPage from '@/pages/admin/AdminTechnicalEndpointsPage.vue';
import { useSessionStore } from '@/stores/session';
import * as trig from '@/lib/triggers';

const EPS: trig.TechnicalEndpoint[] = [
  {
    id: 'e1',
    name: 'BMA Halle 7',
    type: 'bma',
    site: 'Nürnberg Hbf',
    provider_id: null,
    external_source_ids: [],
    default_priority: 'high',
    enabled: true,
    active_config_version: 1,
  },
];

beforeEach(() => {
  setActivePinia(createPinia());
  vi.restoreAllMocks();
  vi.spyOn(trig.technicalEndpointsApi, 'list').mockResolvedValue(EPS);
});

async function factory(perms: string[]) {
  const s = useSessionStore();
  s.user = { id: 'me', display_name: 'Me', status: 'active' };
  s.permissions = perms;
  const i18n = createI18n({ legacy: false, locale: 'de', messages: { de } });
  const w = mount(AdminTechnicalEndpointsPage, { global: { plugins: [i18n] } });
  await new Promise((r) => setTimeout(r, 0));
  await w.vm.$nextTick();
  return w;
}

describe('AdminTechnicalEndpointsPage', () => {
  it('lists endpoints with a translated type', async () => {
    const w = await factory(['technical_endpoints.view']);
    expect(w.text()).toContain('BMA Halle 7');
    expect(w.text()).toContain('Nürnberg Hbf');
    expect(w.text()).not.toContain('Endpunkt anlegen'); // no manage perm
  });

  it('creates an endpoint', async () => {
    const create = vi.spyOn(trig.technicalEndpointsApi, 'create').mockResolvedValue({
      ...EPS[0],
      id: 'e2',
      name: 'Taster Süd',
      type: 'panic_button',
    });
    const w = await factory(['technical_endpoints.view', 'technical_endpoints.manage']);
    await w.get('.card-head .btn.primary').trigger('click');
    await w.get('.te__create input').setValue('Taster Süd');
    await w.findAll('.te__create select')[0].setValue('panic_button');
    await w.get('.te__create').trigger('submit');
    expect(create).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'Taster Süd', type: 'panic_button' }),
    );
  });
});
