import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
// the component reads the active pinia set in beforeEach — do not pass a second
// instance to `mount` or `withPerms` and the component diverge.
import { createI18n } from 'vue-i18n';
import de from '@/i18n/de.json';
import CameraPanel from '@/components/events/CameraPanel.vue';
import { useSessionStore } from '@/stores/session';
import * as cams from '@/lib/cameras';

const i18n = createI18n({ legacy: false, locale: 'de', messages: { de } });

function withPerms(...perms: string[]) {
  const s = useSessionStore();
  s.user = { id: 'u1', display_name: 'Op', status: 'active' };
  s.permissions = perms;
}

async function factory() {
  const w = mount(CameraPanel, {
    props: { eventId: 'ev-1' },
    global: { plugins: [i18n] },
  });
  await flushPromises();
  return w;
}

beforeEach(() => {
  setActivePinia(createPinia());
  vi.restoreAllMocks();
});

describe('CameraPanel (E16-12 / #357)', () => {
  it('lists the associated cameras with a textual status', async () => {
    withPerms('integrations.view');
    vi.spyOn(cams.camerasApi, 'forEvent').mockResolvedValue({
      provider_available: true,
      cameras: [
        {
          ref: 'CAM-1',
          name: 'Bahnsteig Nord',
          site: 'SP Nürnberg',
          online: true,
          group_ids: [],
          last_action_state: 'opened',
        },
        {
          ref: 'CAM-2',
          name: 'Halle 7',
          site: null,
          online: false,
          group_ids: [],
          last_action_state: 'failed',
        },
      ],
    });
    const w = await factory();

    const items = w.findAll('.campanel__item');
    expect(items).toHaveLength(2);
    expect(items[0].text()).toContain('Bahnsteig Nord');
    expect(items[0].find('.campanel__status--online').text()).toBe('verfügbar');
    expect(items[1].find('.campanel__status--offline').text()).toBe('offline');
    // a failed open is called out as text, not just colour
    expect(items[1].text()).toContain('Öffnen fehlgeschlagen');
  });

  it('shows "Video derzeit nicht verfügbar" when the provider is down', async () => {
    withPerms('integrations.view');
    vi.spyOn(cams.camerasApi, 'forEvent').mockResolvedValue({
      provider_available: false,
      cameras: [
        { ref: 'CAM-9', name: 'CAM-9', site: null, online: null, group_ids: [], last_action_state: 'opened' },
      ],
    });
    const w = await factory();

    const down = w.find('.campanel__down');
    expect(down.exists()).toBe(true);
    expect(down.attributes('role')).toBe('status');
    expect(w.find('.campanel__status--unknown').text()).toBe('Status unbekannt');
  });

  it('renders nothing for an event with no associated cameras', async () => {
    withPerms('integrations.view');
    vi.spyOn(cams.camerasApi, 'forEvent').mockResolvedValue({
      provider_available: true,
      cameras: [],
    });
    const w = await factory();
    expect(w.find('.campanel').exists()).toBe(false);
  });

  it('does not render or call the API without integrations.view', async () => {
    withPerms('events.view');
    const spy = vi.spyOn(cams.camerasApi, 'forEvent').mockResolvedValue({
      provider_available: true,
      cameras: [],
    });
    const w = await factory();
    expect(spy).not.toHaveBeenCalled();
    expect(w.find('.campanel').exists()).toBe(false);
  });

  it('stays hidden (never blocks the event) when the request fails', async () => {
    withPerms('integrations.view');
    vi.spyOn(cams.camerasApi, 'forEvent').mockRejectedValue(new Error('boom'));
    const w = await factory();
    expect(w.find('.campanel').exists()).toBe(false);
  });
});
