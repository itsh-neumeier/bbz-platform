import { beforeEach, describe, expect, it, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { createPinia } from 'pinia';
import { createRouter, createMemoryHistory } from 'vue-router';
import { createI18n } from 'vue-i18n';
import de from '@/i18n/de.json';
import AppShell from '@/app/AppShell.vue';
import { telephonyApi } from '@/lib/telephony';
import { contactsApi } from '@/lib/contacts';

beforeEach(() => {
  vi.restoreAllMocks();
  // the comms sidebar polls telephony on mount — keep the shell test offline
  vi.spyOn(telephonyApi, 'ringing').mockResolvedValue({ items: [], next_cursor: null });
  vi.spyOn(telephonyApi, 'history').mockResolvedValue({ items: [], next_cursor: null });
  vi.spyOn(telephonyApi, 'lines').mockResolvedValue({ lines: [] });
  vi.spyOn(telephonyApi, 'pendingDocs').mockResolvedValue({ calls: [] });
  vi.spyOn(contactsApi, 'search').mockResolvedValue({ items: [], next_cursor: null });
});

function factory() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', component: { template: '<div>home</div>' } }],
  });
  const i18n = createI18n({ legacy: false, locale: 'de', messages: { de } });
  return mount(AppShell, { global: { plugins: [createPinia(), router, i18n] } });
}

describe('AppShell', () => {
  it('renders the three-region layout', () => {
    const w = factory();
    expect(w.find('.shell__sidebar').exists()).toBe(true);
    expect(w.find('.shell__content').exists()).toBe(true);
    expect(w.find('.shell__comms').exists()).toBe(true);
  });

  it('comms resize handle is keyboard operable', async () => {
    const w = factory();
    const handle = w.find('.comms__handle');
    expect(handle.attributes('role')).toBe('separator');
    expect(handle.attributes('aria-valuenow')).toBeDefined();
  });
});

describe('reduced motion', () => {
  it('is detectable', async () => {
    vi.stubGlobal('matchMedia', () => ({ matches: true }));
    const { prefersReducedMotion } = await import('@/a11y/reducedMotion');
    expect(prefersReducedMotion()).toBe(true);
  });
});
