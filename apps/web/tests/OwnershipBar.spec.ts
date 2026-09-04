import { beforeEach, describe, expect, it, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { createPinia, setActivePinia } from 'pinia';
import de from '@/i18n/de.json';
import OwnershipBar from '@/components/events/OwnershipBar.vue';
import { useSessionStore } from '@/stores/session';
import { useEventsStore } from '@/stores/events';
import * as ev from '@/lib/events';
import * as apiClient from '@/lib/apiClient';

const detail = (over: Partial<ev.EventDetail> = {}): ev.EventDetail => ({
  id: 'e1',
  title: 'BMA',
  priority: 'critical',
  status: 'opened',
  bbz_id: null,
  workplace_id: null,
  assignee_id: null,
  version: 4,
  created_at: '2026-01-01T08:00:00Z',
  updated_at: '2026-01-01T08:00:00Z',
  description: null,
  status_history: [],
  notes: [],
  ...over,
});

beforeEach(() => {
  setActivePinia(createPinia());
  vi.restoreAllMocks();
  vi.spyOn(apiClient.api, 'get').mockResolvedValue({ state: 'available' } as never);
  vi.spyOn(apiClient.api, 'put').mockResolvedValue({} as never);
  vi.spyOn(useEventsStore(), 'loadDetail').mockResolvedValue(undefined as never);
});

async function factory(perms: string[]) {
  const s = useSessionStore();
  s.user = { id: 'me', display_name: 'Me', status: 'active' };
  s.permissions = perms;
  vi.spyOn(ev.eventsApi, 'assignable').mockResolvedValue({
    users: [
      { id: 'me', display_name: 'Me' },
      { id: 'u2', display_name: 'Kollegin' },
    ],
  });
  const i18n = createI18n({ legacy: false, locale: 'de', messages: { de } });
  const w = mount(OwnershipBar, { props: { event: detail() }, global: { plugins: [i18n] } });
  await new Promise((r) => setTimeout(r, 0));
  await w.vm.$nextTick();
  return w;
}

describe('OwnershipBar', () => {
  it('assigns the event to a chosen operator (events.assign)', async () => {
    const assign = vi.spyOn(ev.eventsApi, 'assign').mockResolvedValue({} as never);
    const w = await factory(['events.assign']);
    const sel = w.get('.own__assign select');
    await sel.setValue('u2');
    expect(assign).toHaveBeenCalledWith('e1', 'u2', 4);
  });

  it('hides the assign control without events.assign', async () => {
    const w = await factory(['events.view']);
    expect(w.find('.own__assign').exists()).toBe(false);
  });
});
