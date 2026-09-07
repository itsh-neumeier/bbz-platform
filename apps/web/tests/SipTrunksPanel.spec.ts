import { beforeEach, describe, expect, it, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import de from '@/i18n/de.json';
import { datetimeFormats } from '@/i18n';
import SipTrunksPanel from '@/components/telephony/SipTrunksPanel.vue';
import * as adminLib from '@/lib/admin';
import { sipTrunkPreset } from '@/lib/sipTrunkPresets';

const TRUNK: adminLib.SipTrunk = {
  trunk_id: 'leonet',
  provider: 'leonet',
  display_name: 'LEONET',
  enabled: true,
  sip_server: 'sip.leovoice.online',
  sip_port: 5060,
  transport: 'udp',
  outbound_proxy: '',
  from_domain: 'sip.leovoice.online',
  registration: true,
  auth_username: 'leo4991150099',
  auth_password_configured: true,
  match_hosts: '91.106.121.3/32',
  codecs: 'alaw,ulaw',
  dtmf_mode: 'rfc4733',
  caller_id_e164: '+4991150099',
};

const NUMBER: adminLib.SipNumber = {
  e164: '+4991150099',
  trunk_id: 'leonet',
  bbz_line_id: 'tor-1',
  label: 'Tor 1',
  registration: false,
  auth_username: '',
  auth_password_configured: false,
  enabled: true,
};

beforeEach(() => {
  vi.restoreAllMocks();
  vi.spyOn(adminLib.adminApi, 'sipTrunks').mockResolvedValue({
    trunks: [structuredClone(TRUNK)],
    numbers: [structuredClone(NUMBER)],
  });
});

async function factory() {
  const i18n = createI18n({ legacy: false, locale: 'de', messages: { de }, datetimeFormats });
  const w = mount(SipTrunksPanel, { global: { plugins: [i18n] } });
  await new Promise((r) => setTimeout(r, 0));
  await w.vm.$nextTick();
  return w;
}

describe('SipTrunksPanel', () => {
  it('lists the trunk and the number and never shows a password', async () => {
    const w = await factory();
    expect(w.get('.sipt__table').text()).toContain('leonet');
    expect(w.text()).toContain('+4991150099');
    expect(w.text()).toContain('Tor 1');
    // no input on the page ever carries a stored password
    expect((w.get('#sipt-pass').element as HTMLInputElement).value).toBe('');
  });

  it('a "loaded" trunk probe shows amber + the registration hint, not a scary "offline"', async () => {
    vi.spyOn(adminLib.adminApi, 'testSipTrunk').mockResolvedValue({
      state: 'loaded',
      detail: "PJSIP/leonet is loaded (ARI: offline). … check 'pjsip show registrations' …",
    });
    const w = await factory();
    const testBtn = w.findAll('button').find((b) => b.text() === de.admin.sipt.test);
    await testBtn!.trigger('click');
    await new Promise((r) => setTimeout(r, 0));
    await w.vm.$nextTick();
    const tag = w.get('.sipt__probe');
    expect(tag.text()).toBe(de.admin.sipt.probe.loaded); // "geladen"
    expect(tag.classes()).toContain('amber');
    expect(w.get('.sipt__probe-detail').text()).toContain('pjsip show registrations');
  });

  it('applying a provider preset fills the technical defaults', async () => {
    const w = await factory();
    await w.get('#sipt-provider').setValue('telekom');
    expect((w.get('#sipt-server').element as HTMLInputElement).value).toBe(
      'reg.sip-trunk.telekom.de',
    );
    expect((w.get('#sipt-transport').element as HTMLSelectElement).value).toBe('tcp');
    expect(w.text()).toContain('gegen Auftragsbestätigung');
  });

  it('saves a trunk without auth_password when the field is blank', async () => {
    const put = vi.spyOn(adminLib.adminApi, 'putSipTrunk').mockResolvedValue(structuredClone(TRUNK));
    const w = await factory();
    await w.get('#sipt-id').setValue('telekom-hbf');
    await w.get('#sipt-server').setValue('reg.sip-trunk.telekom.de');
    await w.get('form.card').trigger('submit');
    await new Promise((r) => setTimeout(r, 0));
    expect(put).toHaveBeenCalledTimes(1);
    expect(put.mock.calls[0][0]).toBe('telekom-hbf');
    expect(put.mock.calls[0][1].auth_password).toBeUndefined();
  });

  it('editing a trunk locks the id and pre-fills the fields', async () => {
    const w = await factory();
    const editBtn = w.findAll('button').find((b) => b.text() === de.admin.sipt.edit);
    await editBtn!.trigger('click');
    expect((w.get('#sipt-id').element as HTMLInputElement).value).toBe('leonet');
    expect(w.get('#sipt-id').attributes('disabled')).toBeDefined();
    expect((w.get('#sipt-server').element as HTMLInputElement).value).toBe('sip.leovoice.online');
  });

  it('edit → save sends only SipTrunkInput fields (no auth_password_configured → no 422)', async () => {
    const put = vi.spyOn(adminLib.adminApi, 'putSipTrunk').mockResolvedValue(structuredClone(TRUNK));
    const w = await factory();
    await w.findAll('button').find((b) => b.text() === de.admin.sipt.edit)!.trigger('click');
    await w.get('#sipt-user').setValue('leo-trunk-user');
    await w.get('#sipt-pass').setValue('trunk-pw');
    await w.get('.sipt form.card').trigger('submit');
    await new Promise((r) => setTimeout(r, 0));

    expect(put).toHaveBeenCalledTimes(1);
    const [id, body] = put.mock.calls[0];
    expect(id).toBe('leonet');
    expect(body).not.toHaveProperty('auth_password_configured');
    expect(body).not.toHaveProperty('trunk_id');
    expect(body.auth_username).toBe('leo-trunk-user');
    expect(body.auth_password).toBe('trunk-pw');
    // the full input shape, nothing more
    expect(Object.keys(body).sort()).toEqual(
      [
        'auth_password',
        'auth_username',
        'caller_id_e164',
        'codecs',
        'display_name',
        'dtmf_mode',
        'enabled',
        'from_domain',
        'match_hosts',
        'outbound_proxy',
        'provider',
        'registration',
        'sip_port',
        'sip_server',
        'transport',
      ].sort(),
    );
  });

  it('renders and copies the generated config', async () => {
    vi.spyOn(adminLib.adminApi, 'sipAsteriskConfig').mockResolvedValue('[leonet]\ntype = endpoint\n');
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, { clipboard: { writeText } });
    const w = await factory();
    const showBtn = w.findAll('button').find((b) => b.text() === de.admin.sipt.showConfig);
    await showBtn!.trigger('click');
    await new Promise((r) => setTimeout(r, 0));
    await w.vm.$nextTick();
    expect(w.get('.sipt__config').text()).toContain('[leonet]');
    const copyBtn = w.findAll('button').find((b) => b.text() === de.admin.sipt.copy);
    await copyBtn!.trigger('click');
    expect(writeText).toHaveBeenCalledWith('[leonet]\ntype = endpoint\n');
  });
});

describe('sipTrunkPreset', () => {
  it('has technical defaults for leonet + telekom and null for generic', () => {
    expect(sipTrunkPreset('leonet')?.sip_server).toBe('sip.leovoice.online');
    expect(sipTrunkPreset('telekom')?.transport).toBe('tcp');
    expect(sipTrunkPreset('generic')).toBeNull();
    // no preset carries credentials
    for (const p of ['leonet', 'telekom'] as const) {
      expect(Object.keys(sipTrunkPreset(p)!)).not.toContain('auth_username');
    }
  });
});
