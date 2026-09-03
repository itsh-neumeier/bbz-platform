import { beforeEach, describe, expect, it, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import { createI18n } from 'vue-i18n';
import { createRouter, createMemoryHistory } from 'vue-router';
import de from '@/i18n/de.json';
import WorkplacePage from '@/pages/WorkplacePage.vue';
import { useSessionStore } from '@/stores/session';
import * as ev from '@/lib/events';
import * as tel from '@/lib/telephony';

const EVENTS: ev.EventListItem[] = [
  { id: 'a', title: 'X', priority: 'critical', status: 'new', bbz_id: null, workplace_id: null, version: 1, assignee_id: null, created_at: '', updated_at: '' },
  { id: 'b', title: 'Y', priority: 'high', status: 'accepted', bbz_id: null, workplace_id: null, version: 1, assignee_id: 'u2', created_at: '', updated_at: '' },
  { id: 'c', title: 'Z', priority: 'low', status: 'new', bbz_id: null, workplace_id: null, version: 1, assignee_id: null, created_at: '', updated_at: '' },
];

beforeEach(() => {
  setActivePinia(createPinia());
  vi.restoreAllMocks();
  vi.spyOn(ev.eventsApi, 'workQueue').mockResolvedValue({ items: EVENTS, next_cursor: null });
  vi.spyOn(ev.eventsApi, 'priorityAlert').mockResolvedValue({
    active: true,
    events: [{ id: 'a', priority: 'critical', title: 'X' }],
  });
  vi.spyOn(tel.telephonyApi, 'ringing').mockResolvedValue({
    items: [{ id: 'r1' } as tel.Call],
    next_cursor: null,
  });
  vi.spyOn(tel.telephonyApi, 'lines').mockResolvedValue({
    lines: [
      { id: 'l1', provider: 'm', external_id: '1', label: null, state: 'in_service', workplace_id: null, updated_at: '' },
      { id: 'l2', provider: 'm', external_id: '2', label: null, state: 'out_of_service', workplace_id: null, updated_at: '' },
    ],
  });
});

async function factory() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/ereignisse', component: { template: '<div/>' } },
      { path: '/telefonbuch', component: { template: '<div/>' } },
      { path: '/wetterlage', component: { template: '<div/>' } },
      { path: '/monitore', component: { template: '<div/>' } },
      { path: '/archiv', component: { template: '<div/>' } },
    ],
  });
  const i18n = createI18n({ legacy: false, locale: 'de', messages: { de } });
  const pinia = createPinia();
  setActivePinia(pinia);
  useSessionStore().user = { id: 'u1', display_name: 'Ops', status: 'active' };
  const w = mount(WorkplacePage, { global: { plugins: [pinia, router, i18n] } });
  await new Promise((r) => setTimeout(r, 0));
  await w.vm.$nextTick();
  await new Promise((r) => setTimeout(r, 0));
  return w;
}

describe('WorkplacePage', () => {
  it('summarises the open queue by priority', async () => {
    const w = await factory();
    expect(w.text()).toContain('Offene Ereignisse');
    // total 3, unassigned 2
    expect(w.get('.wp__n').text()).toBe('3');
    expect(w.text()).toContain('2 ohne Bearbeiter');
    const prio = w.get('.wp__card--prio');
    expect(prio.text()).toMatch(/kritisch\s*1/);
    expect(prio.text()).toMatch(/hoch\s*1/);
  });

  it('shows the unaccepted high/critical alert', async () => {
    const w = await factory();
    const alert = w.get('.wp__alert');
    expect(alert.classes()).toContain('wp__alert--critical');
    expect(alert.text()).toContain('hoher Priorität');
  });

  it('shows waiting calls and line status', async () => {
    const w = await factory();
    expect(w.text()).toContain('Wartende Anrufe');
    expect(w.text()).toContain('1 von 2 Leitungen in Betrieb');
  });

  it('degrades to zeros when the feeds fail', async () => {
    vi.mocked(ev.eventsApi.workQueue).mockRejectedValue(new Error('nope'));
    vi.mocked(tel.telephonyApi.ringing).mockRejectedValue(new Error('nope'));
    vi.mocked(tel.telephonyApi.lines).mockRejectedValue(new Error('nope'));
    vi.mocked(ev.eventsApi.priorityAlert).mockRejectedValue(new Error('nope'));
    const w = await factory();
    expect(w.get('.wp__n').text()).toBe('0');
    expect(w.find('.wp__alert').exists()).toBe(false);
  });
});
