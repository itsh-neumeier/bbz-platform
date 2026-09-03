import { beforeEach, describe, expect, it, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import { createI18n } from 'vue-i18n';
import { createRouter, createMemoryHistory } from 'vue-router';
import de from '@/i18n/de.json';
import EventsPage from '@/pages/EventsPage.vue';
import { useSessionStore } from '@/stores/session';
import * as ev from '@/lib/events';

const li = (over: Partial<ev.EventListItem>): ev.EventListItem => ({
  id: 'x',
  title: 'X',
  priority: 'low',
  status: 'new',
  bbz_id: null,
  workplace_id: null,
  version: 1,
  assignee_id: null,
  created_at: '2026-09-03T10:00:00Z',
  updated_at: '2026-09-03T10:00:00Z',
  ...over,
});

const ALL: ev.EventListItem[] = [
  li({ id: 'a', title: 'BMA Halle 7', priority: 'critical', status: 'opened', created_at: '2026-09-03T12:00:00Z' }),
  li({ id: 'b', title: 'Alt-Fund', priority: 'low', status: 'archived', created_at: '2026-09-03T09:00:00Z' }),
  li({ id: 'c', title: 'RI-Störung Erlangen', priority: 'medium', status: 'new', created_at: '2026-09-03T11:00:00Z' }),
];

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(ev.eventsApi, 'list').mockResolvedValue({ items: ALL, next_cursor: null });
  vi.spyOn(ev.eventsApi, 'priorityAlert').mockResolvedValue({ active: false, events: [] });
  vi.spyOn(ev.eventsApi, 'get').mockResolvedValue({
    ...ALL[0],
    description: 'BMA',
    status_history: [],
    notes: [],
  });
  vi.spyOn(ev.eventsApi, 'workflow').mockRejectedValue(new Error('none'));
});

const flush = async () => {
  await new Promise((r) => setTimeout(r, 0));
  await new Promise((r) => setTimeout(r, 0));
};

async function factory(query: Record<string, string> = {}) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/ereignisse', name: 'events', component: EventsPage },
      { path: '/ereignisse/:id', name: 'event-detail', component: { template: '<div/>' } },
    ],
  });
  await router.push({ path: '/ereignisse', query });
  const pinia = createPinia();
  setActivePinia(pinia);
  useSessionStore().user = { id: 'u1', display_name: 'Ops', status: 'active' };
  const i18n = createI18n({ legacy: false, locale: 'de', messages: { de } });
  const w = mount(EventsPage, { global: { plugins: [pinia, router, i18n] } });
  await flush();
  return w;
}

describe('EventsPage — Ereignisübersicht', () => {
  it('lists active and archived events, newest active first, archived last', async () => {
    const w = await factory();
    const titles = w.findAll('.events__title').map((n) => n.text());
    // a (12:00) newer than c (11:00); b is archived → last regardless of time
    expect(titles).toEqual(['BMA Halle 7', 'RI-Störung Erlangen', 'Alt-Fund']);
    expect(w.findAll('.events__row--archived')).toHaveLength(1);
  });

  it('filters to archived only', async () => {
    const w = await factory({ archiv: '1' });
    const titles = w.findAll('.events__title').map((n) => n.text());
    expect(titles).toEqual(['Alt-Fund']);
  });

  it('searches by title', async () => {
    const w = await factory();
    await w.get('input[type="search"]').setValue('erlangen');
    expect(w.findAll('.events__title').map((n) => n.text())).toEqual(['RI-Störung Erlangen']);
  });

  it('opens the processing panel for a clicked row', async () => {
    const w = await factory();
    expect(w.text()).toContain('auswählen');
    await w.findAll('.events__row')[0].trigger('click'); // BMA Halle 7 (id 'a')
    await flush();
    expect(ev.eventsApi.get).toHaveBeenCalledWith('a');
    expect(w.text()).toContain('BMA Halle 7');
  });
});
