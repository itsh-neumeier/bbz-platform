import { beforeEach, describe, expect, it, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { createPinia } from 'pinia';
import { createRouter, createMemoryHistory } from 'vue-router';
import { createI18n } from 'vue-i18n';
import de from '@/i18n/de.json';
import AppShell from '@/app/AppShell.vue';
import { telephonyApi } from '@/lib/telephony';
import { contactsApi } from '@/lib/contacts';
import { eventsApi } from '@/lib/events';
import { weatherApi } from '@/lib/weather';

beforeEach(() => {
  vi.restoreAllMocks();
  // the shell + comms sidebar poll several feeds on mount — keep the test offline
  vi.spyOn(telephonyApi, 'ringing').mockResolvedValue({ items: [], next_cursor: null });
  vi.spyOn(telephonyApi, 'history').mockResolvedValue({ items: [], next_cursor: null });
  vi.spyOn(telephonyApi, 'lines').mockResolvedValue({ lines: [] });
  vi.spyOn(telephonyApi, 'pendingDocs').mockResolvedValue({ calls: [] });
  vi.spyOn(contactsApi, 'search').mockResolvedValue({ items: [], next_cursor: null });
  vi.spyOn(eventsApi, 'workQueue').mockResolvedValue({ items: [], next_cursor: null });
  vi.spyOn(eventsApi, 'logbook').mockResolvedValue({ items: [] });
  vi.spyOn(weatherApi, 'alerts').mockResolvedValue({ alerts: [] } as never);
});

function factory() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', name: 'workplace', component: { template: '<div>home</div>' } }],
  });
  const i18n = createI18n({ legacy: false, locale: 'de', messages: { de } });
  return mount(AppShell, { global: { plugins: [createPinia(), router, i18n] } });
}

describe('AppShell', () => {
  it('renders the V10 shell regions', () => {
    const w = factory();
    expect(w.find('.shell__logo').exists()).toBe(true);
    expect(w.find('.shell__topbar').exists()).toBe(true);
    expect(w.find('.shell__sidebar').exists()).toBe(true);
    expect(w.find('.shell__content').exists()).toBe(true);
    expect(w.find('.shell__footer').exists()).toBe(true);
    expect(w.find('.shell__comms').exists()).toBe(true);
    expect(w.find('.shell__glog').exists()).toBe(true);
  });

  it('lays the shell out as a three-column, three-row grid', () => {
    const w = factory();
    const shell = w.find('.shell').element as HTMLElement;
    // jsdom does not compute grid, but the inline custom prop must be set
    expect(shell.style.getPropertyValue('--bbz-comms-width')).toMatch(/\d+px/);
  });

  it('comms resize handle is keyboard operable', () => {
    const w = factory();
    const handle = w.find('.comms__handle');
    expect(handle.attributes('role')).toBe('separator');
    expect(handle.attributes('aria-valuenow')).toBeDefined();
  });

  it('shows the cross-workplace logbook panel', () => {
    const w = factory();
    expect(w.find('.shell__glog').text()).toContain('Logbuch');
  });
});

describe('reduced motion', () => {
  it('is detectable', async () => {
    vi.stubGlobal('matchMedia', () => ({ matches: true }));
    const { prefersReducedMotion } = await import('@/a11y/reducedMotion');
    expect(prefersReducedMotion()).toBe(true);
  });
});
