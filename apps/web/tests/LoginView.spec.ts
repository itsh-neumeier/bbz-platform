import { beforeEach, describe, expect, it, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import { createI18n } from 'vue-i18n';
import { createRouter, createMemoryHistory } from 'vue-router';
import de from '@/i18n/de.json';
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
  const i18n = createI18n({ legacy: false, locale: 'de', messages: { de } });
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
});
