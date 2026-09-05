import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { createPinia, setActivePinia } from 'pinia';
import { createMemoryHistory, createRouter } from 'vue-router';
import de from '@/i18n/de.json';
import WeatherPage from '@/pages/WeatherPage.vue';
import { useSessionStore } from '@/stores/session';
import * as weather from '@/lib/weather';

const HEALTH: weather.WeatherHealth = {
  overall: 'ok',
  checked_at: '2026-09-05T11:00:00Z',
  kinds: [
    { data_kind: 'warnings', status: 'ok', last_success_at: null, last_error: null, age_seconds: 10 },
    {
      data_kind: 'observations',
      status: 'stale',
      last_success_at: null,
      last_error: null,
      age_seconds: 99999,
    },
    { data_kind: 'radar', status: 'ok', last_success_at: null, last_error: null, age_seconds: 5 },
  ],
};

const ALERT: weather.WeatherAlert = {
  id: 'al-1',
  region: 'Nürnberg',
  type: 'STURMBÖEN',
  level: '3',
  valid_from: '2026-09-05T12:00:00Z',
  valid_to: '2026-09-05T20:00:00Z',
  headline: 'Amtliche Warnung vor STURMBÖEN',
  description: 'Böen bis 90 km/h.',
  source_ref: 'DWD-1',
  received_at: '2026-09-05T11:00:00Z',
};

const OBS: weather.WeatherObservation = {
  place: 'Nürnberg',
  metric: 'wind_speed',
  value: 42,
  unit: 'km/h',
  observed_at: '2026-09-05T10:50:00Z',
  station_ref: 'P-NUE',
};

function mockApi() {
  vi.spyOn(weather.weatherApi, 'alerts').mockResolvedValue({
    attribution: 'Deutscher Wetterdienst',
    health: HEALTH,
    alerts: [ALERT],
  });
  vi.spyOn(weather.weatherApi, 'observations').mockResolvedValue({
    attribution: 'Deutscher Wetterdienst',
    health: HEALTH,
    observations: [OBS],
  });
  vi.spyOn(weather.weatherApi, 'radar').mockResolvedValue({
    attribution: 'Deutscher Wetterdienst',
    health: HEALTH,
    area: 'mittelfranken',
    frames: [],
  });
}

function withPerms(...perms: string[]) {
  const s = useSessionStore();
  s.user = { id: 'u1', display_name: 'Op', status: 'active' };
  s.permissions = perms;
}

const router = createRouter({
  history: createMemoryHistory(),
  routes: [
    { path: '/wetterlage', component: WeatherPage },
    { path: '/ereignisse/:id', component: { template: '<div>event</div>' } },
  ],
});

async function factory() {
  const i18n = createI18n({ legacy: false, locale: 'de', messages: { de } });
  await router.push('/wetterlage');
  const w = mount(WeatherPage, { global: { plugins: [router, i18n], stubs: { teleport: true } } });
  await flushPromises();
  return w;
}

beforeEach(() => {
  setActivePinia(createPinia());
  vi.restoreAllMocks();
  mockApi();
});

describe('WeatherPage (E18-09 / #391)', () => {
  it('renders warnings, observation tiles, the health badge and DWD attribution', async () => {
    withPerms('weather.view');
    const w = await factory();
    expect(w.get('.wx__alert').text()).toContain('Amtliche Warnung vor STURMBÖEN');
    expect(w.get('.wx__tile').text()).toContain('42 km/h');
    expect(w.find('.wx__health--ok').exists()).toBe(true);
    expect(w.get('.wx__attr').text()).toContain('Deutscher Wetterdienst');
  });

  it('marks a stale data kind on its panel', async () => {
    withPerms('weather.view');
    const w = await factory();
    // observations kind is stale in HEALTH
    const obs = w.get('#wx-obs');
    expect(obs.find('.wx__stale').exists()).toBe(true);
    expect(w.get('#wx-alerts').find('.wx__stale').exists()).toBe(false);
  });

  it('hides "Ereignis erzeugen" without weather.create_event', async () => {
    withPerms('weather.view');
    const w = await factory();
    expect(w.find('.wx__create').exists()).toBe(false);
  });

  it('opens the confirmation dialog and creates the event, then navigates to it', async () => {
    withPerms('weather.view', 'weather.create_event');
    const create = vi.spyOn(weather.weatherApi, 'createEvent').mockResolvedValue({
      event_id: 'ev-9',
      weather_alert_id: 'al-1',
      source_ref: 'DWD-1',
      priority: 'high',
      created: true,
    });
    const push = vi.spyOn(router, 'push');
    const w = await factory();

    await w.get('.wx__create').trigger('click');
    await flushPromises();
    expect(w.find('.wxd__form').exists()).toBe(true);

    await w.get('#wxd-assessment').setValue('Dach am Bahnsteig prüfen');
    await w.get('.wxd__form').trigger('submit');
    await flushPromises();

    expect(create).toHaveBeenCalledWith('al-1', {
      priority: 'high',
      assessment: 'Dach am Bahnsteig prüfen',
    });
    expect(push).toHaveBeenCalledWith('/ereignisse/ev-9');
  });

  it('shows the load error banner when the feed is unreachable', async () => {
    withPerms('weather.view');
    vi.spyOn(weather.weatherApi, 'alerts').mockRejectedValue(new Error('boom'));
    const w = await factory();
    expect(w.get('.wx__error').attributes('role')).toBe('alert');
  });
});
