import { describe, expect, it } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import de from '@/i18n/de.json';
import WeatherEventDialog from '@/components/weather/WeatherEventDialog.vue';
import type { WeatherAlert } from '@/lib/weather';

const i18n = createI18n({ legacy: false, locale: 'de', messages: { de } });

const ALERT: WeatherAlert = {
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

async function factory(props: Partial<InstanceType<typeof WeatherEventDialog>['$props']> = {}) {
  const w = mount(WeatherEventDialog, {
    props: { open: true, alert: ALERT, busy: false, ...props },
    global: { plugins: [i18n] },
    attachTo: document.body,
  });
  await flushPromises();
  return w;
}

describe('WeatherEventDialog (E18-09 / #391)', () => {
  it('pre-fills the priority from the DWD warn level (3 → hoch)', async () => {
    const w = await factory();
    expect((w.get('#wxd-prio').element as HTMLSelectElement).value).toBe('high');
    expect(w.get('.wxd__lead').text()).toContain('Amtliche Warnung vor STURMBÖEN');
    expect(w.get('.wxd__lead').text()).toContain('Nürnberg');
  });

  it('confirms with the chosen priority and the trimmed assessment', async () => {
    const w = await factory();
    await w.get('#wxd-prio').setValue('critical');
    await w.get('#wxd-assessment').setValue('  Bahnhofsdach prüfen  ');
    await w.get('.wxd__form').trigger('submit');

    const ev = w.emitted('confirm');
    expect(ev).toHaveLength(1);
    expect(ev![0][0]).toEqual({ priority: 'critical', assessment: 'Bahnhofsdach prüfen' });
  });

  it('confirms with an empty assessment when none is given', async () => {
    const w = await factory();
    await w.get('.wxd__form').trigger('submit');
    expect(w.emitted('confirm')![0][0]).toEqual({ priority: 'high', assessment: '' });
  });

  it('emits close on cancel', async () => {
    const w = await factory();
    await w.get('.wxd__cancel').trigger('click');
    expect(w.emitted('close')).toHaveLength(1);
  });

  it('shows a server error and disables confirm while busy', async () => {
    const w = await factory({ busy: true, error: 'Kaputt.' });
    expect(w.get('.wxd__error').text()).toBe('Kaputt.');
    expect(w.get('.wxd__confirm').attributes('disabled')).toBeDefined();
  });
});
