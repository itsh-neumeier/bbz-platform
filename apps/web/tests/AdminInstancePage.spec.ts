import { beforeEach, describe, expect, it, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { createPinia, setActivePinia } from 'pinia';
import de from '@/i18n/de.json';
import AdminInstancePage from '@/pages/admin/AdminInstancePage.vue';
import { useSessionStore } from '@/stores/session';
import * as admin from '@/lib/admin';

const GROUPS: admin.AdminSettingGroup[] = [
  {
    group: 'instance',
    label: 'Instanz',
    items: [
      {
        key: 'instance.name',
        name: 'name',
        label: 'Name der BBZ-Instanz',
        help: 'z. B. BBZ Nürnberg',
        kind: 'str',
        secret: false,
        value: 'BBZ / 3-S-Zentrale',
        configured: null,
        source: 'default',
        overridden: false,
      },
      {
        key: 'instance.short_name',
        name: 'short_name',
        label: 'Kurzname',
        help: '',
        kind: 'str',
        secret: false,
        value: 'BBZ',
        configured: null,
        source: 'default',
        overridden: false,
      },
    ],
  },
];

beforeEach(() => {
  setActivePinia(createPinia());
  vi.restoreAllMocks();
  vi.spyOn(admin.adminApi, 'settings').mockResolvedValue({ groups: GROUPS });
  const s = useSessionStore();
  s.user = { id: 'u1', display_name: 'Admin', status: 'active' };
  s.permissions = ['system.settings.manage'];
});

async function factory() {
  const i18n = createI18n({ legacy: false, locale: 'de', messages: { de } });
  const w = mount(AdminInstancePage, { global: { plugins: [i18n] } });
  await new Promise((r) => setTimeout(r, 0));
  await w.vm.$nextTick();
  return w;
}

describe('AdminInstancePage', () => {
  it('renders a field per non-secret instance setting with its source', async () => {
    const w = await factory();
    expect(w.get('#ai-name').element).toBeInstanceOf(HTMLInputElement);
    expect((w.get('#ai-name').element as HTMLInputElement).value).toBe('BBZ / 3-S-Zentrale');
    expect(w.get('#ai-short_name').element).toBeTruthy();
    expect(w.text()).toContain('Standardwert');
  });

  it('saves only the changed values and reloads meta', async () => {
    const update = vi.spyOn(admin.adminApi, 'updateSettings').mockResolvedValue({
      updated: ['instance.name'],
      groups: [
        {
          ...GROUPS[0],
          items: [
            { ...GROUPS[0].items[0], value: 'BBZ Nürnberg', source: 'database', overridden: true },
            GROUPS[0].items[1],
          ],
        },
      ],
    });
    const loadMeta = vi
      .spyOn(useSessionStore(), 'loadMeta')
      .mockResolvedValue(undefined as unknown as void);

    const w = await factory();
    await w.get('#ai-name').setValue('BBZ Nürnberg');
    await w.get('form').trigger('submit');
    await new Promise((r) => setTimeout(r, 0));

    expect(update).toHaveBeenCalledWith('instance', { 'instance.name': 'BBZ Nürnberg' });
    expect(loadMeta).toHaveBeenCalled();
    expect(w.text()).toContain('Gespeichert');
  });

  it('disables save until a field changes', async () => {
    const w = await factory();
    const btn = w.get('button[type="submit"]');
    expect(btn.attributes('disabled')).toBeDefined();
    await w.get('#ai-name').setValue('Anders');
    expect(btn.attributes('disabled')).toBeUndefined();
  });
});
