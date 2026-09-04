import { beforeEach, describe, expect, it, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { createPinia, setActivePinia } from 'pinia';
import de from '@/i18n/de.json';
import AdminDirectoryPage from '@/pages/admin/AdminDirectoryPage.vue';
import { useSessionStore } from '@/stores/session';
import * as adminLib from '@/lib/admin';
import * as dir from '@/lib/directory';
import * as usersLib from '@/lib/users';

const SETTINGS: adminLib.AdminSettingsResponse = {
  groups: [
    {
      group: 'directory',
      label: 'Verzeichnis (LDAP)',
      items: [
        {
          key: 'directory.ldap_url',
          name: 'ldap_url',
          label: 'LDAP-URL(s)',
          help: '',
          kind: 'str',
          secret: false,
          value: 'ldaps://dc.example:636',
          configured: null,
          source: 'database',
          overridden: true,
        },
        {
          key: 'directory.ldap_bind_password',
          name: 'ldap_bind_password',
          label: 'Bind-Passwort',
          help: '',
          kind: 'str',
          secret: true,
          value: null,
          configured: true,
          source: 'environment',
          overridden: false,
        },
      ],
    },
  ],
};

beforeEach(() => {
  setActivePinia(createPinia());
  vi.restoreAllMocks();
  vi.spyOn(adminLib.adminApi, 'settings').mockResolvedValue(SETTINGS);
  vi.spyOn(usersLib.rolesApi, 'list').mockResolvedValue([
    { id: 'r1', key: 'disponent', name: 'Disponent', builtin: true },
  ]);
  vi.spyOn(dir.groupMappingsApi, 'list').mockResolvedValue({
    mappings: [{ id: 'm1', provider: 'ldap_ad', external_group: 'leitstelle', role_key: 'disponent' }],
  });
  vi.spyOn(dir.directoryApi, 'syncState').mockResolvedValue({
    source: 'ldap_ad',
    last_run_at: '2026-09-04T06:00:00Z',
    last_success_at: '2026-09-04T06:00:00Z',
    last_error: null,
    last_summary: null,
  });
});

async function factory(perms: string[]) {
  const s = useSessionStore();
  s.user = { id: 'me', display_name: 'Me', status: 'active' };
  s.permissions = perms;
  const i18n = createI18n({ legacy: false, locale: 'de', messages: { de } });
  const w = mount(AdminDirectoryPage, { global: { plugins: [i18n] } });
  await new Promise((r) => setTimeout(r, 0));
  await new Promise((r) => setTimeout(r, 0));
  await w.vm.$nextTick();
  return w;
}

describe('AdminDirectoryPage', () => {
  it('shows the connection fields, the bind-pw status and existing mappings', async () => {
    const w = await factory(['system.settings.manage', 'roles.manage', 'users.manage']);
    expect((w.get('#d-ldap_url').element as HTMLInputElement).value).toBe('ldaps://dc.example:636');
    expect(w.text()).toContain('gesetzt'); // bind pw configured
    expect(w.text()).toContain('leitstelle');
    expect(w.find('.dir__banner').exists()).toBe(false); // configured → no warning
  });

  it('runs the connection test and renders the structured result', async () => {
    const test = vi.spyOn(dir.directoryApi, 'test').mockResolvedValue({
      configured: true,
      reachable: true,
      tls_ok: true,
      bind_ok: false,
      sample_count: null,
      error: 'service bind failed: invalid credentials',
    });
    const w = await factory(['system.settings.manage']);
    await w.get('.card-head .btn.ghost.sm').trigger('click');
    await new Promise((r) => setTimeout(r, 0));
    expect(test).toHaveBeenCalled();
    expect(w.get('.dir__test').text()).toContain('Service-Bind');
    expect(w.get('.dir__test-err').text()).toContain('invalid credentials');
  });

  it('adds a group→role mapping', async () => {
    const create = vi.spyOn(dir.groupMappingsApi, 'create').mockResolvedValue({
      id: 'm2',
      provider: 'ldap_ad',
      external_group: 'sichtleiter',
      role_key: 'disponent',
    });
    const w = await factory(['system.settings.manage', 'roles.manage']);
    await w.get('.dir__map-add input').setValue('sichtleiter');
    await w.get('.dir__map-add select').setValue('disponent');
    await w.get('.dir__map-add').trigger('submit');
    expect(create).toHaveBeenCalledWith('ldap_ad', 'sichtleiter', 'disponent');
  });

  it('triggers a dry-run sync', async () => {
    const run = vi.spyOn(dir.directoryApi, 'runSync').mockResolvedValue({
      source: 'ldap_ad',
      ok: true,
      dry_run: true,
      aborted: false,
      error: null,
      scanned: 12,
      created: 0,
      deactivated: 0,
      errors: [],
      created_uids: [],
      deactivated_uids: [],
    });
    const w = await factory(['system.settings.manage', 'users.manage']);
    await w.get('.dir__sync-run .btn.primary').trigger('click');
    await new Promise((r) => setTimeout(r, 0));
    expect(run).toHaveBeenCalledWith(true); // dry-run default
    expect(w.get('.dir__report').text()).toContain('12 geprüft');
  });

  it('warns when no LDAP url is configured', async () => {
    vi.spyOn(adminLib.adminApi, 'settings').mockResolvedValue({
      groups: [
        {
          group: 'directory',
          label: 'x',
          items: [{ ...SETTINGS.groups[0].items[0], value: '', source: 'default', overridden: false }],
        },
      ],
    });
    const w = await factory(['system.settings.manage']);
    expect(w.find('.dir__banner').exists()).toBe(true);
  });
});
