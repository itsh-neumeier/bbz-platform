import { beforeEach, describe, expect, it, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import de from '@/i18n/de.json';
import MonitorPage from '@/pages/MonitorPage.vue';
import * as mon from '@/lib/monitor';

const routes: mon.MonitorRoutes = {
  inputs: [
    { key: 'bbz-os', label: 'BBZ-OS' },
    { key: 'bku3', label: 'BKU 3' },
    { key: 'coda1', label: 'Coda 1' },
  ],
  outputs: [
    { key: 'workplace3', label: 'Arbeitsplatzmonitor 3', grid_row: 0, grid_col: 2, is_large_display: false, is_fixed: false },
    { key: 'workplace4', label: 'Arbeitsplatzmonitor 4', grid_row: 1, grid_col: 0, is_large_display: false, is_fixed: true },
    { key: 'large-display', label: 'Großbild', grid_row: null, grid_col: null, is_large_display: true, is_fixed: false },
  ],
  routes: [
    { output_key: 'workplace3', input_key: 'bku3', is_fixed: false, set_at: '' },
    { output_key: 'workplace4', input_key: 'bbz-os', is_fixed: true, set_at: '' },
    { output_key: 'large-display', input_key: 'coda1', is_fixed: false, set_at: '' },
  ],
  provider_available: true,
  provider_healthy: true,
};

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(mon.monitorApi, 'routes').mockResolvedValue(routes);
  vi.spyOn(mon.monitorApi, 'profiles').mockResolvedValue({ profiles: [] });
});

async function factory() {
  const i18n = createI18n({ legacy: false, locale: 'de', messages: { de } });
  const w = mount(MonitorPage, { global: { plugins: [i18n] } });
  await new Promise((r) => setTimeout(r, 0));
  await w.vm.$nextTick();
  return w;
}

describe('MonitorPage', () => {
  it('renders the grid + large display and locks the fixed output', async () => {
    const w = await factory();
    expect(w.findAll('.mon__cell')).toHaveLength(3);
    const selects = w.findAll('select');
    // workplace4 (is_fixed) select is disabled
    const wp4 = w.findAll('.mon__cell').find((c) => c.text().includes('Arbeitsplatzmonitor 4'))!;
    expect(wp4.find('select').attributes('disabled')).toBeDefined();
    expect(wp4.text()).toContain('BBZ-OS');
    expect(selects.length).toBeGreaterThanOrEqual(3);
  });

  it('PUTs the single assignment when an output select changes', async () => {
    const setRoutes = vi.spyOn(mon.monitorApi, 'setRoutes').mockResolvedValue(routes);
    const w = await factory();
    const wp3 = w.findAll('.mon__cell').find((c) => c.text().includes('Arbeitsplatzmonitor 3'))!;
    await wp3.find('select').setValue('coda1');
    expect(setRoutes).toHaveBeenCalledWith({ workplace3: 'coda1' });
  });

  it('resets to the standard layout', async () => {
    const reset = vi.spyOn(mon.monitorApi, 'resetStandard').mockResolvedValue(routes);
    const w = await factory();
    await w.get('.mon__actions button').trigger('click');
    expect(reset).toHaveBeenCalled();
  });
});
