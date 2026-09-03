import { beforeEach, describe, expect, it } from 'vitest';
import { mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { createPinia, setActivePinia } from 'pinia';
import { RouterLinkStub } from '@vue/test-utils';
import de from '@/i18n/de.json';
import AdminPage from '@/pages/admin/AdminPage.vue';
import { useSessionStore } from '@/stores/session';
import { ADMIN_SECTIONS } from '@/lib/admin';

beforeEach(() => {
  setActivePinia(createPinia());
});

async function factory(perms: string[]) {
  const s = useSessionStore();
  s.user = { id: 'u1', display_name: 'Admin', status: 'active' };
  s.permissions = perms;

  const i18n = createI18n({ legacy: false, locale: 'de', messages: { de } });
  const w = mount(AdminPage, {
    global: {
      plugins: [i18n],
      stubs: { RouterLink: RouterLinkStub, RouterView: true },
    },
  });
  await w.vm.$nextTick();
  return w;
}

describe('AdminPage', () => {
  it('shows only the sub-sections the user is permitted', async () => {
    const w = await factory(['system.settings.manage', 'users.manage']);
    const items = w.findAll('.admin__nav-item').map((n) => n.text());
    // instance + directory (both system.settings.manage) + users
    expect(items).toContain('Instanz');
    expect(items).toContain('Benutzer');
    expect(items).toContain('Verzeichnis');
    expect(items).not.toContain('Integrationen');
    expect(items).not.toContain('System');
  });

  it('shows every section for a full admin', async () => {
    const w = await factory([...new Set(ADMIN_SECTIONS.map((s) => s.perm))]);
    expect(w.findAll('.admin__nav-item')).toHaveLength(ADMIN_SECTIONS.length);
  });

  it('renders no nav for a user with no manage permission', async () => {
    const w = await factory(['events.view']);
    expect(w.findAll('.admin__nav-item')).toHaveLength(0);
  });
});
