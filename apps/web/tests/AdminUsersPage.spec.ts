import { beforeEach, describe, expect, it, vi } from 'vitest';
import { mount, RouterLinkStub } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { createPinia, setActivePinia } from 'pinia';
import de from '@/i18n/de.json';
import AdminUsersPage from '@/pages/admin/AdminUsersPage.vue';
import { useSessionStore } from '@/stores/session';
import * as users from '@/lib/users';

const USERS: users.AdminUser[] = [
  {
    id: 'u1',
    display_name: 'Anna Admin',
    status: 'active',
    external_ref: null,
    roles: ['administrator'],
    providers: ['local'],
  },
  {
    id: 'u2',
    display_name: 'Bob Disponent',
    status: 'disabled',
    external_ref: null,
    roles: [],
    providers: ['ldap_ad'],
  },
];

const ROLES: users.Role[] = [
  { id: 'r1', key: 'administrator', name: 'Administrator', builtin: true },
  { id: 'r2', key: 'disponent', name: 'Disponent', builtin: true },
];

beforeEach(() => {
  setActivePinia(createPinia());
  vi.restoreAllMocks();
  vi.spyOn(users.usersApi, 'list').mockResolvedValue(USERS);
  vi.spyOn(users.rolesApi, 'list').mockResolvedValue(ROLES);
});

async function factory(perms: string[]) {
  const s = useSessionStore();
  s.user = { id: 'me', display_name: 'Me', status: 'active' };
  s.permissions = perms;
  const i18n = createI18n({ legacy: false, locale: 'de', messages: { de } });
  const w = mount(AdminUsersPage, {
    global: { plugins: [i18n], stubs: { RouterLink: RouterLinkStub } },
  });
  await new Promise((r) => setTimeout(r, 0));
  await w.vm.$nextTick();
  return w;
}

describe('AdminUsersPage', () => {
  it('lists users with providers and role names', async () => {
    const w = await factory(['users.view']);
    const rows = w.findAll('.au__row');
    expect(rows).toHaveLength(2);
    expect(rows[0].text()).toContain('Anna Admin');
    expect(rows[0].text()).toContain('Administrator'); // role key → name
    expect(rows[0].text()).toContain('local');
    expect(rows[1].classes()).toContain('au__row--off'); // disabled
  });

  it('hides create + role editing without users.manage / roles.manage', async () => {
    const w = await factory(['users.view']);
    expect(w.text()).not.toContain('Konto anlegen');
    await w.findAll('.au__row')[0].trigger('click');
    expect(w.get('.au__roles').attributes('disabled')).toBeDefined();
  });

  it('creates a local account and selects it', async () => {
    const created: users.AdminUser = {
      id: 'u3',
      display_name: 'Neu',
      status: 'active',
      external_ref: null,
      roles: [],
      providers: ['local'],
    };
    const create = vi.spyOn(users.usersApi, 'create').mockResolvedValue(created);
    const w = await factory(['users.view', 'users.manage']);
    await w.get('.btn.primary.sm').trigger('click'); // "Konto anlegen"
    await w.get('.au__create input').setValue('Neu');
    const inputs = w.findAll('.au__create input');
    await inputs[1].setValue('neu');
    await inputs[2].setValue('Wolke7-Bahnhof!x');
    await w.get('.au__create').trigger('submit');
    await new Promise((r) => setTimeout(r, 0));
    expect(create).toHaveBeenCalledWith({
      display_name: 'Neu',
      local_username: 'neu',
      initial_password: 'Wolke7-Bahnhof!x',
    });
  });

  it('assigns a role via the checkbox', async () => {
    const assign = vi.spyOn(users.rolesApi, 'assign').mockResolvedValue(undefined as unknown as void);
    vi.spyOn(users.usersApi, 'get').mockResolvedValue({ ...USERS[0], roles: ['administrator', 'disponent'] });
    const w = await factory(['users.view', 'users.manage', 'roles.manage']);
    await w.findAll('.au__row')[0].trigger('click');
    const boxes = w.findAll('.au__role input');
    await boxes[1].setValue(true); // disponent
    expect(assign).toHaveBeenCalledWith('u1', 'r2');
  });

  it('deactivates with a confirm', async () => {
    vi.stubGlobal('confirm', () => true);
    const deact = vi
      .spyOn(users.usersApi, 'deactivate')
      .mockResolvedValue({ sessions_revoked: 2 });
    vi.spyOn(users.usersApi, 'get').mockResolvedValue({ ...USERS[0], status: 'disabled' });
    const w = await factory(['users.view', 'users.manage']);
    await w.findAll('.au__row')[0].trigger('click');
    await w.get('.au__detail-actions .btn.danger').trigger('click');
    expect(deact).toHaveBeenCalledWith('u1');
  });
});
