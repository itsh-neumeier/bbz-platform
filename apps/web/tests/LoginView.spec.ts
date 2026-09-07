import { beforeEach, describe, expect, it, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import { createI18n } from 'vue-i18n';
import { createRouter, createMemoryHistory } from 'vue-router';
import de from '@/i18n/de.json';
import { datetimeFormats } from '@/i18n';
import LoginView from '@/features/auth/LoginView.vue';
import { useSessionStore } from '@/stores/session';

function factory() {
  setActivePinia(createPinia());
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/login', component: LoginView },
      { path: '/', component: { template: '<div />' } },
    ],
  });
  const i18n = createI18n({ legacy: false, locale: 'de', messages: { de }, datetimeFormats });
  const w = mount(LoginView, { global: { plugins: [createPinia(), router, i18n] } });
  return { w, router };
}

beforeEach(() => vi.restoreAllMocks());

describe('LoginView', () => {
  it('shows username + password on the first step', () => {
    const { w } = factory();
    expect(w.find('input[name="username"]').exists()).toBe(true);
    expect(w.find('input[name="password"]').exists()).toBe(true);
    expect(w.find('input[name="totp"]').exists()).toBe(false);
  });

  it('shows the DB InfraGO brand mark above the instance title', () => {
    const { w } = factory();
    const brand = w.find('.login__brand');
    expect(brand.exists()).toBe(true);
    expect(brand.text()).toContain('DB InfraGO AG');
    expect(brand.text()).toContain('Personenbahnhöfe');
    // the card order: brand, then the instance-name <h1>
    expect(w.find('.login__card > .login__brand + .login__title').exists()).toBe(true);
  });

  it('renders the BBZ-OS version footer from /meta', async () => {
    const { w } = factory();
    useSessionStore().meta = {
      service: 'bbz',
      version: '1.4.2',
      api_version: 'v1',
      environment: 'production',
      node_id: 'BBZ-NBG-01',
      instance_name: 'BBZ / 3-S-Zentrale',
      instance_short_name: 'BBZ',
      capabilities: [],
      known_integrations: [],
    };
    await w.vm.$nextTick();
    const foot = w.find('.login__foot');
    expect(foot.text()).toContain('BBZ-OS');
    expect(foot.text()).toContain('1.4.2');
    expect(foot.text()).toContain('Produktionsumgebung');
    expect(foot.text()).toContain('BBZ-NBG-01');
  });

  it('the footer degrades when /meta is unavailable', () => {
    const { w } = factory();
    expect(w.find('.login__foot').text()).toContain('nicht verfügbar');
  });

  it('switches to the TOTP step when the server asks for it', async () => {
    const { w } = factory();
    vi.spyOn(useSessionStore(), 'login').mockResolvedValue({ kind: 'totp' });
    await w.find('input[name="username"]').setValue('a');
    await w.find('input[name="password"]').setValue('b');
    await w.find('form').trigger('submit');
    await w.vm.$nextTick();
    expect(w.find('input[name="totp"]').exists()).toBe(true);
  });

  it('renders a German error for bad credentials', async () => {
    const { w } = factory();
    const { ApiError } = await import('@/lib/apiClient');
    vi.spyOn(useSessionStore(), 'login').mockRejectedValue(
      new ApiError(401, { code: 'unauthorized', message: 'invalid credentials' }),
    );
    await w.find('input[name="username"]').setValue('a');
    await w.find('input[name="password"]').setValue('b');
    await w.find('form').trigger('submit');
    await w.vm.$nextTick();
    expect(w.find('[role="alert"]').text()).toContain('Benutzername oder Passwort');
  });

  it('shows the forced change form and submits current + new password (#97)', async () => {
    const { w, router } = factory();
    const session = useSessionStore();
    vi.spyOn(session, 'login').mockImplementation(async () => {
      session.mustChangePassword = true;
      return { kind: 'none' };
    });
    const change = vi.spyOn(session, 'changePassword').mockResolvedValue(undefined);

    await w.find('input[name="username"]').setValue('op');
    await w.find('input[name="password"]').setValue('old-secret');
    await w.find('form').trigger('submit');
    await w.vm.$nextTick();

    // the credential inputs are gone, the new-password inputs are shown
    expect(w.find('input[name="username"]').exists()).toBe(false);
    expect(w.find('input[name="new-password"]').exists()).toBe(true);

    await w.find('input[name="new-password"]').setValue('Fjord-Nebel-42!x');
    await w.find('input[name="confirm-password"]').setValue('Fjord-Nebel-42!x');
    await w.find('form').trigger('submit');
    await w.vm.$nextTick();

    expect(change).toHaveBeenCalledWith('old-secret', 'Fjord-Nebel-42!x');
    await new Promise((r) => setTimeout(r, 0));
    expect(router.currentRoute.value.path).toBe('/');
  });

  it('blocks the forced change when the two passwords differ (#97)', async () => {
    const { w } = factory();
    const session = useSessionStore();
    session.mustChangePassword = true;
    const change = vi.spyOn(session, 'changePassword').mockResolvedValue(undefined);
    await w.vm.$nextTick();

    await w.find('input[name="new-password"]').setValue('Fjord-Nebel-42!x');
    await w.find('input[name="confirm-password"]').setValue('different');
    await w.find('form').trigger('submit');
    await w.vm.$nextTick();

    expect(change).not.toHaveBeenCalled();
    expect(w.find('.login__error').text()).toContain('stimmen nicht überein');
  });
});
