import { beforeEach, describe, expect, it, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import { createI18n } from 'vue-i18n';
import { createRouter, createMemoryHistory } from 'vue-router';
import de from '@/i18n/de.json';
import WorkplacePage from '@/pages/WorkplacePage.vue';
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

const EVENTS: ev.EventListItem[] = [
  li({ id: 'a', title: 'BMA Halle 7', priority: 'critical', status: 'new' }),
  li({ id: 'b', title: 'Aufzug', priority: 'high', status: 'accepted', assignee_id: 'u1' }),
  li({ id: 'c', title: 'RI-Störung', priority: 'low', status: 'new' }),
];

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(ev.eventsApi, 'workQueue').mockResolvedValue({ items: EVENTS, next_cursor: null });
  vi.spyOn(ev.eventsApi, 'priorityAlert').mockResolvedValue({ active: false, events: [] });
  vi.spyOn(ev.eventsApi, 'get').mockResolvedValue({
    ...EVENTS[0],
    description: 'BMA',
    status_history: [{ from_status: null, to_status: 'new', changed_at: '2026-09-03T10:00:00Z', changed_by: null }],
    notes: [],
  });
  vi.spyOn(ev.eventsApi, 'workflow').mockRejectedValue(new Error('none'));
});

async function factory() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/ereignisse', name: 'events', component: { template: '<div/>' } },
      { path: '/ereignisse/:id', name: 'event-detail', component: { template: '<div/>' } },
      { path: '/archiv', name: 'archive', component: { template: '<div/>' } },
    ],
  });
  const pinia = createPinia();
  setActivePinia(pinia);
  useSessionStore().user = { id: 'u1', display_name: 'Ops', status: 'active' };
  useSessionStore().permissions = ['events.accept', 'events.acknowledge', 'events.open', 'events.archive'];
  const w = mount(WorkplacePage, { global: { plugins: [pinia, router, i18n()] } });
  await flush();
  return w;
}
const i18n = () => createI18n({ legacy: false, locale: 'de', messages: { de } });
const flush = async () => {
  await new Promise((r) => setTimeout(r, 0));
  await new Promise((r) => setTimeout(r, 0));
};

describe('WorkplacePage — Ereignisspeicher', () => {
  it('renders a row per queued event, critical first', async () => {
    const w = await factory();
    const rows = w.findAll('.wp__row');
    expect(rows).toHaveLength(3);
    expect(rows[0].text()).toContain('BMA Halle 7');
  });

  it('counts open / unhandled / mine', async () => {
    const w = await factory();
    const text = w.get('.wp__counters').text();
    expect(text).toMatch(/Offen\s*3/);
    expect(text).toMatch(/Unbearbeitet\s*2/);
    expect(text).toMatch(/Mein Arbeitsplatz\s*1/);
  });

  it('pulses critical and high rows', async () => {
    const w = await factory();
    const rows = w.findAll('.wp__row');
    expect(rows[0].classes()).toContain('wp__row--critical');
    expect(rows[1].classes()).toContain('wp__row--high');
    expect(rows[2].classes()).not.toContain('wp__row--high');
  });

  it('shows all four lifecycle actions per row, disabled by status', async () => {
    const w = await factory();
    const firstRowButtons = w.findAll('.wp__row')[0].findAll('button');
    const labels = firstRowButtons.map((b) => b.text());
    expect(labels).toEqual(['Annehmen', 'Quittieren', 'Öffnen', 'Archivieren']);
    // status "new" → only Annehmen enabled
    expect(firstRowButtons[0].attributes('disabled')).toBeUndefined();
    expect(firstRowButtons[1].attributes('disabled')).toBeDefined();
  });

  it('opens the processing panel inline when a row is clicked', async () => {
    const w = await factory();
    expect(w.find('.wp__processing-empty').exists()).toBe(true);
    await w.findAll('.wp__row')[0].trigger('click');
    await flush();
    expect(w.find('.wp__processing-empty').exists()).toBe(false);
    expect(w.text()).toContain('BMA Halle 7');
    expect(ev.eventsApi.get).toHaveBeenCalledWith('a');
  });
});
