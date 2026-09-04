import { beforeEach, describe, expect, it, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { createPinia, setActivePinia } from 'pinia';
import de from '@/i18n/de.json';
import AdminIntegrationsPage from '@/pages/admin/AdminIntegrationsPage.vue';
import { useSessionStore } from '@/stores/session';
import * as adminLib from '@/lib/admin';

const DOMAINS: adminLib.DomainIntegration[] = [
  {
    domain: 'weather',
    setting_key: 'integrations.weather',
    active_id: 'dwd',
    source: 'default',
    available: [
      { id: 'dwd', name: 'DWD Open Data', mock: false, version: '0.1.0' },
      { id: 'dwd_mock', name: 'DWD Mock', mock: true, version: '0.1.0' },
    ],
    active_is_mock: false,
    health: { state: 'ok', summary: 'fresh' },
  },
  {
    domain: 'video',
    setting_key: 'integrations.video',
    active_id: 'coda_video',
    source: 'database',
    available: [{ id: 'coda_video', name: 'Coda Video', mock: true, version: '0.1.0' }],
    active_is_mock: true,
    health: { state: 'degraded', summary: 'no vendor API' },
  },
];

beforeEach(() => {
  setActivePinia(createPinia());
  vi.restoreAllMocks();
  vi.spyOn(adminLib.adminApi, 'integrations').mockResolvedValue({ domains: DOMAINS });
});

async function factory(perms: string[]) {
  const s = useSessionStore();
  s.user = { id: 'me', display_name: 'Me', status: 'active' };
  s.permissions = perms;
  const i18n = createI18n({ legacy: false, locale: 'de', messages: { de } });
  const w = mount(AdminIntegrationsPage, { global: { plugins: [i18n] } });
  await new Promise((r) => setTimeout(r, 0));
  await w.vm.$nextTick();
  return w;
}

describe('AdminIntegrationsPage', () => {
  it('shows a card per domain with health and mock badges', async () => {
    const w = await factory(['integrations.view']);
    const cards = w.findAll('.ig__grid .card');
    expect(cards).toHaveLength(2);
    expect(cards[0].text()).toContain('Wetter');
    expect(cards[0].text()).toContain('betriebsbereit');
    expect(cards[1].text()).toContain('nur Mock');
  });

  it('changes the active adapter through the settings API', async () => {
    const upd = vi
      .spyOn(adminLib.adminApi, 'updateSettings')
      .mockResolvedValue({ updated: ['integrations.weather'], groups: [] });
    const w = await factory(['integrations.view', 'integrations.configure']);
    await w.get('#ig-weather').setValue('dwd_mock');
    expect(upd).toHaveBeenCalledWith('integrations', { 'integrations.weather': 'dwd_mock' });
  });

  it('disables the select without integrations.configure', async () => {
    const w = await factory(['integrations.view']);
    expect(w.get('#ig-weather').attributes('disabled')).toBeDefined();
  });
});
