import { beforeEach, describe, expect, it, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { createPinia, setActivePinia } from 'pinia';
import de from '@/i18n/de.json';
import { datetimeFormats } from '@/i18n';
import AdminTelephonyPage from '@/pages/admin/AdminTelephonyPage.vue';
import * as adminLib from '@/lib/admin';

const CONFIG: adminLib.SipConfig = {
  gateway: {
    instance_id: 'sip',
    kind: 'asterisk_ari',
    host: 'pbx.test',
    port: 8088,
    tls: true,
    app_name: 'bbz-sip',
    dtmf_transport: 'rfc2833',
    ari_username: 'bbz',
    ari_password_configured: true,
    enabled: false,
    created_at: null,
    updated_at: null,
  },
  lines: [
    {
      bbz_line_id: '1001',
      asterisk_endpoint: 'PJSIP/1001',
      label: 'Tor 1',
      enabled: true,
      ring_moh_file_id: null,
      hold_moh_file_id: null,
    },
  ],
  active: false,
};

beforeEach(() => {
  setActivePinia(createPinia());
  vi.restoreAllMocks();
  vi.spyOn(adminLib.adminApi, 'sipConfig').mockResolvedValue(structuredClone(CONFIG));
  // the embedded <SipTrunksPanel> loads on mount
  vi.spyOn(adminLib.adminApi, 'sipTrunks').mockResolvedValue({ trunks: [], numbers: [] });
  vi.spyOn(adminLib.adminApi, 'sipMohFiles').mockResolvedValue({ files: [] });
});

async function factory() {
  const i18n = createI18n({ legacy: false, locale: 'de', messages: { de }, datetimeFormats });
  const w = mount(AdminTelephonyPage, { global: { plugins: [i18n] } });
  await new Promise((r) => setTimeout(r, 0));
  await w.vm.$nextTick();
  return w;
}

describe('AdminTelephonyPage', () => {
  it('populates the form from the stored config and shows the line', async () => {
    const w = await factory();
    expect((w.get('#sip-host').element as HTMLInputElement).value).toBe('pbx.test');
    expect((w.get('#sip-user').element as HTMLInputElement).value).toBe('bbz');
    expect(w.get('.sip__table').text()).toContain('1001');
    // password is never populated — only the "keep" placeholder
    expect((w.get('#sip-pass').element as HTMLInputElement).value).toBe('');
    expect(w.get('#sip-pass').attributes('placeholder')).toContain('Passwort gesetzt');
  });

  it('saves without ari_password when the field is left blank', async () => {
    const put = vi
      .spyOn(adminLib.adminApi, 'putSipGateway')
      .mockResolvedValue(structuredClone(CONFIG));
    const w = await factory();
    await w.get('#sip-host').setValue('pbx2.test');
    await w.get('form.card').trigger('submit');
    expect(put).toHaveBeenCalledTimes(1);
    expect(put.mock.calls[0][0]).toMatchObject({ host: 'pbx2.test' });
    expect(put.mock.calls[0][0].ari_password).toBeUndefined();
  });

  it('sends the typed password when the field is filled', async () => {
    const put = vi
      .spyOn(adminLib.adminApi, 'putSipGateway')
      .mockResolvedValue(structuredClone(CONFIG));
    const w = await factory();
    await w.get('#sip-pass').setValue('new-pw');
    await w.get('form.card').trigger('submit');
    expect(put.mock.calls[0][0].ari_password).toBe('new-pw');
  });

  it('shows the "not the active provider" note', async () => {
    const w = await factory();
    expect(w.text()).toContain('nicht telephony_sip');
  });

  it('probes the connection and renders the result', async () => {
    vi.spyOn(adminLib.adminApi, 'testSipConnection').mockResolvedValue({
      reachable: false,
      detail: 'Asterisk ARI unreachable: refused',
      asterisk_version: null,
    });
    const w = await factory();
    await w.get('button.btn:not(.btn--primary)').trigger('click');
    await new Promise((r) => setTimeout(r, 0));
    await w.vm.$nextTick();
    expect(w.text()).toContain('nicht erreichbar');
    expect(w.text()).toContain('unreachable: refused');
  });

  it('uploads a MoH file and assigns it as a line’s hold music (#817)', async () => {
    const moh: adminLib.SipMohFile = {
      id: 'moh-1',
      name: 'Bahnhofsmusik',
      original_filename: 'b.wav',
      mime: 'audio/wav',
      size_bytes: 2048,
      sha256: 'abc',
      uploaded_at: '2026-09-08T10:00:00Z',
      used_by: [],
    };
    vi.mocked(adminLib.adminApi.sipMohFiles)
      .mockResolvedValueOnce({ files: [] })
      .mockResolvedValue({ files: [moh] });
    const upload = vi.spyOn(adminLib.adminApi, 'uploadSipMoh').mockResolvedValue(moh);
    const putLine = vi
      .spyOn(adminLib.adminApi, 'putSipLine')
      .mockResolvedValue({ ...CONFIG.lines[0], hold_moh_file_id: 'moh-1' });
    const w = await factory();

    const file = new File([new Uint8Array([1, 2, 3])], 'b.wav', { type: 'audio/wav' });
    const input = w.get('input[type="file"]').element as HTMLInputElement;
    Object.defineProperty(input, 'files', { value: [file] });
    await w.get('input[type="file"]').trigger('change');
    await w.findAll('form.sip__add').at(-1)!.trigger('submit');
    await new Promise((r) => setTimeout(r, 0));
    await w.vm.$nextTick();

    expect(upload).toHaveBeenCalledWith('b.wav', file);
    expect(w.text()).toContain('Bahnhofsmusik');

    // assign it as the line's hold music via the dropdown
    const holdSelect = w.findAll('.sip__table select')[1];
    await holdSelect.setValue('moh-1');
    expect(putLine).toHaveBeenCalledWith(
      '1001',
      expect.objectContaining({ hold_moh_file_id: 'moh-1' }),
    );
  });
});
