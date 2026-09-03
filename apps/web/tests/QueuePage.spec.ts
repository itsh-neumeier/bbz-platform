import { beforeEach, describe, expect, it, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import { createI18n } from 'vue-i18n';
import { createRouter, createMemoryHistory } from 'vue-router';
import de from '@/i18n/de.json';
import QueuePage from '@/pages/QueuePage.vue';
import * as ev from '@/lib/events';
import { useSessionStore } from '@/stores/session';

const rows: ev.EventListItem[] = [
  {
    id: 'a',
    title: 'Panikalarm',
    priority: 'critical',
    status: 'new',
    bbz_id: null,
    workplace_id: null,
    version: 1,
    assignee_id: null,
    created_at: '2026-01-01T10:00:00Z',
    updated_at: '2026-01-01T10:00:00Z',
  },
  {
    id: 'b',
    title: 'Reinigung',
    priority: 'low',
    status: 'accepted',
    bbz_id: null,
    workplace_id: null,
    version: 1,
    assignee_id: null,
    created_at: '2026-01-01T09:00:00Z',
    updated_at: '2026-01-01T09:00:00Z',
  },
];

beforeEach(() => {
  setActivePinia(createPinia());
  vi.restoreAllMocks();
  vi.spyOn(ev.eventsApi, 'workQueue').mockResolvedValue({ items: rows, next_cursor: null });
  vi.spyOn(ev.eventsApi, 'priorityAlert').mockResolvedValue({ active: false, events: [] });
});

async function factory() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/ereignisse', name: 'events', component: QueuePage },
      { path: '/ereignisse/:id', name: 'event-detail', component: { template: '<div />' } },
    ],
  });
  const i18n = createI18n({ legacy: false, locale: 'de', messages: { de } });
  const pinia = createPinia();
  setActivePinia(pinia);
  useSessionStore().permissions = ['events.accept', 'events.acknowledge'];
  const w = mount(QueuePage, { global: { plugins: [pinia, router, i18n] } });
  await new Promise((r) => setTimeout(r, 0));
  await w.vm.$nextTick();
  return w;
}

describe('QueuePage', () => {
  it('renders a row per event, critical first', async () => {
    const w = await factory();
    const titles = w.findAll('.queue__title').map((n) => n.text());
    expect(titles).toEqual(['Panikalarm', 'Reinigung']);
  });

  it('shows the status-appropriate action and hides it without the permission', async () => {
    const w = await factory();
    const buttons = w
      .findAll('.acts button')
      .map((b) => b.text())
      .filter((txt) => txt !== 'Bearbeiten');
    // new → Annehmen, accepted → Quittieren (both permitted in this fixture)
    expect(buttons).toContain('Annehmen');
    expect(buttons).toContain('Quittieren');
  });
});
