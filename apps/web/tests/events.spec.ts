import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import { useEventsStore } from '@/stores/events';
import * as ev from '@/lib/events';
import { ConflictError } from '@/lib/apiClient';

const item = (over: Partial<ev.EventListItem>): ev.EventListItem => ({
  id: 'e1',
  title: 't',
  priority: 'medium',
  status: 'new',
  bbz_id: null,
  workplace_id: null,
  version: 1,
  assignee_id: null,
  created_at: '2026-01-01T10:00:00Z',
  updated_at: '2026-01-01T10:00:00Z',
  ...over,
});

beforeEach(() => {
  setActivePinia(createPinia());
  vi.restoreAllMocks();
});

describe('events store', () => {
  it('orders the queue by priority rank then age', () => {
    const s = useEventsStore();
    s.queue = [
      item({ id: 'a', priority: 'low', created_at: '2026-01-01T09:00:00Z' }),
      item({ id: 'b', priority: 'critical', created_at: '2026-01-01T12:00:00Z' }),
      item({ id: 'c', priority: 'critical', created_at: '2026-01-01T11:00:00Z' }),
      item({ id: 'd', priority: 'high', created_at: '2026-01-01T08:00:00Z' }),
    ];
    expect(s.sortedQueue.map((e) => e.id)).toEqual(['c', 'b', 'd', 'a']);
  });

  it('applies a transition using the row version and updates status', async () => {
    const s = useEventsStore();
    s.queue = [item({ id: 'e1', status: 'new', version: 3 })];
    const spy = vi.spyOn(ev.eventsApi, 'transition').mockResolvedValue({
      id: 'e1',
      title: 't',
      description: null,
      priority: 'medium',
      status: 'accepted',
      bbz_id: null,
      workplace_id: null,
      version: 4,
    });
    vi.spyOn(ev.eventsApi, 'priorityAlert').mockResolvedValue({ active: false, events: [] });

    await s.transition('e1', 'accept');

    expect(spy).toHaveBeenCalledWith('e1', 'accept', 3);
    expect(s.queue[0].status).toBe('accepted');
    expect(s.queue[0].version).toBe(4);
  });

  it('drops an archived event from the queue', async () => {
    const s = useEventsStore();
    s.queue = [item({ id: 'e1', status: 'opened', version: 1 })];
    vi.spyOn(ev.eventsApi, 'transition').mockResolvedValue({
      id: 'e1',
      title: 't',
      description: null,
      priority: 'low',
      status: 'archived',
      bbz_id: null,
      workplace_id: null,
      version: 2,
    });
    vi.spyOn(ev.eventsApi, 'priorityAlert').mockResolvedValue({ active: false, events: [] });

    await s.transition('e1', 'archive');
    expect(s.queue).toHaveLength(0);
  });

  it('refreshes on a version conflict and rethrows', async () => {
    const s = useEventsStore();
    s.queue = [item({ id: 'e1', status: 'new', version: 1 })];
    vi.spyOn(ev.eventsApi, 'transition').mockRejectedValue(
      new ConflictError(409, { code: 'conflict', message: 'stale', details: { expected_version: 2 } }),
    );
    const reload = vi.spyOn(ev.eventsApi, 'workQueue').mockResolvedValue({ items: [], next_cursor: null });

    await expect(s.transition('e1', 'accept')).rejects.toBeInstanceOf(ConflictError);
    expect(reload).toHaveBeenCalled();
  });
});
