/**
 * SIP-Trunk-Provider-Presets (ADR-0034, §"Provider presets are UI-only").
 *
 * NUR technische Defaults (Registrar, Port, Transport, Codecs, DTMF) — **keine**
 * Zugangsdaten, keine kundenspezifischen Realms/Proxies. Der Betreiber trägt
 * `auth_username` / Passwort / ggf. abweichende Hosts aus der
 * Auftragsbestätigung ein. LEONET: aus der Standalone-Lösung des Betreibers.
 * Telekom: die öffentlich dokumentierten DeutschlandLAN-SIP-Trunk-Parameter
 * (`reg.sip-trunk.telekom.de`, TCP). Beides „gegen Auftragsbestätigung prüfen".
 */
import type { SipTrunkDtmfMode, SipTrunkProvider, SipTrunkTransport } from '@/lib/admin';

export interface SipTrunkPreset {
  sip_server: string;
  sip_port: number;
  transport: SipTrunkTransport;
  outbound_proxy: string;
  from_domain: string;
  registration: boolean;
  match_hosts: string;
  codecs: string;
  dtmf_mode: SipTrunkDtmfMode;
}

export const SIP_TRUNK_PRESETS: Record<Exclude<SipTrunkProvider, 'generic'>, SipTrunkPreset> = {
  leonet: {
    sip_server: 'sip.leovoice.online',
    sip_port: 5060,
    transport: 'udp',
    outbound_proxy: '',
    from_domain: 'sip.leovoice.online',
    registration: true,
    match_hosts: '91.106.121.3/32',
    codecs: 'alaw,ulaw',
    dtmf_mode: 'rfc4733',
  },
  telekom: {
    sip_server: 'reg.sip-trunk.telekom.de',
    sip_port: 5060,
    transport: 'tcp',
    outbound_proxy: '',
    from_domain: 'sip-trunk.telekom.de',
    registration: true,
    match_hosts: '',
    codecs: 'alaw,ulaw,g722',
    dtmf_mode: 'rfc4733',
  },
};

export function sipTrunkPreset(provider: SipTrunkProvider): SipTrunkPreset | null {
  return provider === 'generic' ? null : SIP_TRUNK_PRESETS[provider];
}
