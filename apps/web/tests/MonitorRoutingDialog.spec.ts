import { beforeEach, describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import de from '@/i18n/de.json';
import MonitorRoutingDialog from '@/components/monitor/MonitorRoutingDialog.vue';
import * as mon from '@/lib/monitor';

const i18n = createI18n({ legacy: false, locale: 'de', messages: { de } });

const ROUTES: mon.MonitorRoutes = {
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

function fakeDataTransfer(seed: Record<string, string> = {}) {
  const store: Record<string, string> = { ...seed };
  return {
    dropEffect: 'none',
    setData: (k: string, v: string) => {
      store[k] = v;
    },
    getData: (k: string) => store[k] ?? '',
  } as unknown as DataTransfer;
}

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(mon.monitorApi, 'routes').mockResolvedValue(ROUTES);
  vi.spyOn(mon.monitorApi, 'profiles').mockResolvedValue({ profiles: [] });
});

async function factory() {
  const w = mount(MonitorRoutingDialog, {
    props: { open: true },
    global: { plugins: [i18n] },
    attachTo: document.body,
  });
  await flushPromises();
  return w;
}

describe('MonitorRoutingDialog (E19-08 / #408)', () => {
  it('renders the 3×2 grid + large display and locks the fixed output', async () => {
    const w = await factory();
    expect(w.findAll('.mrd__output')).toHaveLength(3);
    const wp4 = w.findAll('.mrd__output').find((c) => c.text().includes('Arbeitsplatzmonitor 4'))!;
    expect(wp4.find('select').attributes('disabled')).toBeDefined();
    expect(wp4.find('.mrd__lock').exists()).toBe(true);
    expect(wp4.text()).toContain('BBZ-OS');
  });

  it('PUTs the single assignment when an output <select> changes (keyboard path)', async () => {
    const setRoutes = vi.spyOn(mon.monitorApi, 'setRoutes').mockResolvedValue(ROUTES);
    const w = await factory();
    const wp3 = w.findAll('.mrd__output').find((c) => c.text().includes('Arbeitsplatzmonitor 3'))!;
    await wp3.find('select').setValue('coda1');
    expect(setRoutes).toHaveBeenCalledWith({ workplace3: 'coda1' });
  });

  it('assigns an input by dropping its chip on an output', async () => {
    const setRoutes = vi.spyOn(mon.monitorApi, 'setRoutes').mockResolvedValue(ROUTES);
    const w = await factory();

    const chip = w.findAll('.mrd__source').find((s) => s.text() === 'Coda 1')!;
    const dt = fakeDataTransfer();
    await chip.trigger('dragstart', { dataTransfer: dt });
    expect(dt.getData('text/plain')).toBe('coda1');

    const wp3 = w.findAll('.mrd__output').find((c) => c.text().includes('Arbeitsplatzmonitor 3'))!;
    await wp3.trigger('dragover', { dataTransfer: dt });
    await wp3.trigger('drop', { dataTransfer: dt });
    expect(setRoutes).toHaveBeenCalledWith({ workplace3: 'coda1' });
  });

  it('never routes a drop onto the fixed output', async () => {
    const setRoutes = vi.spyOn(mon.monitorApi, 'setRoutes').mockResolvedValue(ROUTES);
    const w = await factory();
    const wp4 = w.findAll('.mrd__output').find((c) => c.text().includes('Arbeitsplatzmonitor 4'))!;
    await wp4.trigger('drop', { dataTransfer: fakeDataTransfer({ 'text/plain': 'coda1' }) });
    expect(setRoutes).not.toHaveBeenCalled();
  });

  it('does not re-PUT when the dropped input already routes there', async () => {
    const setRoutes = vi.spyOn(mon.monitorApi, 'setRoutes').mockResolvedValue(ROUTES);
    const w = await factory();
    const wp3 = w.findAll('.mrd__output').find((c) => c.text().includes('Arbeitsplatzmonitor 3'))!;
    await wp3.trigger('drop', { dataTransfer: fakeDataTransfer({ 'text/plain': 'bku3' }) });
    expect(setRoutes).not.toHaveBeenCalled();
  });

  it('resets to the standard layout', async () => {
    const reset = vi.spyOn(mon.monitorApi, 'resetStandard').mockResolvedValue(ROUTES);
    const w = await factory();
    await w.get('.mrd__std').trigger('click');
    expect(reset).toHaveBeenCalled();
  });

  it('saves a profile from the current layout', async () => {
    const save = vi.spyOn(mon.monitorApi, 'saveProfile').mockResolvedValue({
      id: 'p1',
      name: 'Nachtdienst',
      scope: 'user',
      workplace_id: null,
      layout: {},
    });
    const w = await factory();
    await w.get('#mrd-pname').setValue('Nachtdienst');
    await w.get('.mrd__profile-save').trigger('submit');
    expect(save).toHaveBeenCalledWith('Nachtdienst', {
      workplace3: 'bku3',
      workplace4: 'bbz-os',
      'large-display': 'coda1',
    });
  });

  it('emits close on the × button', async () => {
    const w = await factory();
    await w.get('.mrd__close').trigger('click');
    expect(w.emitted('close')).toHaveLength(1);
  });
});
