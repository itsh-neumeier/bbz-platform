import { beforeEach, describe, expect, it, vi } from 'vitest';
import { mount, RouterLinkStub } from '@vue/test-utils';
import { createPinia, setActivePinia } from 'pinia';
import { createI18n } from 'vue-i18n';
import de from '@/i18n/de.json';
import CommsSidebar from '@/app/components/CommsSidebar.vue';
import { useSessionStore } from '@/stores/session';
import * as tel from '@/lib/telephony';
import * as ct from '@/lib/contacts';

const ringing: tel.Call = {
  id: 'call-1',
  bbz_call_id: 'CALL-20260903-AAAA',
  provider: 'telephony_mock',
  direction: 'inbound',
  state: 'ringing',
  line_id: 'l1',
  workplace_id: null,
  started_at: '2026-09-03T10:00:00Z',
  ended_at: null,
  created_at: '2026-09-03T10:00:00Z',
  category: null,
  has_free_text: false,
  caller_contact_id: null,
  caller_priority: 'high',
  participants: [{ number: '+4991123', display_name: 'Leitwarte', role: 'caller' }],
};

function mockApis() {
  vi.spyOn(tel.telephonyApi, 'ringing').mockResolvedValue({ items: [ringing], next_cursor: null });
  vi.spyOn(tel.telephonyApi, 'history').mockResolvedValue({ items: [], next_cursor: null });
  vi.spyOn(tel.telephonyApi, 'lines').mockResolvedValue({
    lines: [
      {
        id: 'l1',
        provider: 'telephony_mock',
        external_id: 'LINE-1',
        label: 'Amt 1',
        state: 'in_service',
        workplace_id: null,
        updated_at: '',
      },
    ],
  });
  vi.spyOn(tel.telephonyApi, 'pendingDocs').mockResolvedValue({ calls: [] });
  vi.spyOn(tel.telephonyApi, 'getDoc').mockResolvedValue({
    call_id: 'call-1',
    category: null,
    free_text: null,
    documented_by: null,
    documented_at: null,
    mandatory_done: false,
  });
  vi.spyOn(ct.contactsApi, 'search').mockResolvedValue({ items: [], next_cursor: null });
}

async function factory(perms: string[]) {
  const i18n = createI18n({ legacy: false, locale: 'de', messages: { de } });
  const pinia = createPinia();
  setActivePinia(pinia);
  useSessionStore().permissions = perms;
  const w = mount(CommsSidebar, {
    global: { plugins: [pinia, i18n], stubs: { RouterLink: RouterLinkStub } },
  });
  await new Promise((r) => setTimeout(r, 0));
  await w.vm.$nextTick();
  await new Promise((r) => setTimeout(r, 0));
  return w;
}

beforeEach(() => {
  vi.restoreAllMocks();
  mockApis();
});

describe('CommsSidebar', () => {
  it('renders the four tabs', async () => {
    const w = await factory(['calls.view']);
    expect(w.findAll('[role="tab"]')).toHaveLength(4);
  });

  it('shows a waiting call with its priority class and an Annehmen button', async () => {
    const w = await factory(['calls.view', 'calls.answer']);
    const item = w.get('.wq__item');
    expect(item.classes()).toContain('wq__item--high');
    expect(item.text()).toContain('Leitwarte');
    expect(item.find('.wq__answer').exists()).toBe(true);
  });

  it('sorts the waiting queue high → low regardless of arrival order (#301)', async () => {
    const mk = (id: string, prio: 'high' | 'medium' | 'low' | null, who: string): tel.Call => ({
      ...ringing,
      id,
      caller_priority: prio,
      participants: [{ number: '+49' + id, display_name: who, role: 'caller' }],
    });
    vi.mocked(tel.telephonyApi.ringing).mockResolvedValue({
      // arrive scrambled
      items: [mk('1', 'low', 'Niedrig'), mk('2', null, 'Unbekannt'), mk('3', 'high', 'Hoch'), mk('4', 'medium', 'Mittel')],
      next_cursor: null,
    });
    const w = await factory(['calls.view']);
    const who = w.findAll('.wq__item .wq__who').map((r) => r.text());
    expect(who).toEqual(['Hoch', 'Mittel', 'Niedrig', 'Unbekannt']);
  });

  it('answers a call and moves to the Gespräch tab', async () => {
    const answer = vi
      .spyOn(tel.telephonyApi, 'answer')
      .mockResolvedValue({ call_id: 'call-1', action: 'answer', accepted: true, detail: null });
    const w = await factory(['calls.view', 'calls.answer']);
    await w.get('.wq__answer').trigger('click');
    expect(answer).toHaveBeenCalledWith('call-1');
  });

  it('builds a number on the keypad and dials it', async () => {
    const dial = vi.spyOn(tel.telephonyApi, 'dial').mockResolvedValue({ accepted: true, detail: null });
    const w = await factory(['calls.view', 'calls.dial']);
    const keys = w.findAll('.tp__key');
    await keys[0].trigger('click'); // 1
    await keys[1].trigger('click'); // 2
    await w.get('.tp__call').trigger('click');
    expect(dial).toHaveBeenCalledWith('l1', '12');
  });

  it('hides the keypad without calls.dial', async () => {
    const w = await factory(['calls.view']);
    expect(w.find('.tp__pad').exists()).toBe(false);
    expect(w.find('.tp__quickdial').exists()).toBe(false);
  });

  it('opens the quick-dial overlay and dials the chosen contact (#225)', async () => {
    const gatehouse: ct.Contact = {
      id: 'c1',
      name: 'Pförtner Haupttor',
      org: 'Werkschutz',
      notes: null,
      quick_dial: true,
      bbz_id: null,
      priority: null,
      created_at: '2026-09-01T08:00:00Z',
      updated_at: '2026-09-01T08:00:00Z',
      numbers: [{ id: 'n1', e164: '+498955501', label: null, is_primary: true }],
    };
    vi.mocked(ct.contactsApi.search).mockResolvedValue({ items: [gatehouse], next_cursor: null });
    const dial = vi.spyOn(tel.telephonyApi, 'dial').mockResolvedValue({ accepted: true, detail: null });
    const w = await factory(['calls.view', 'calls.dial']);

    await w.get('.tp__quickdial').trigger('click');
    await new Promise((r) => setTimeout(r, 0));
    await w.vm.$nextTick();

    const item = w.get('.qd__item');
    expect(item.text()).toContain('Pförtner Haupttor');
    await item.trigger('click');

    expect(dial).toHaveBeenCalledWith('l1', '+498955501');
  });

  it('flags mandatory documentation on a pending-doc call', async () => {
    vi.mocked(tel.telephonyApi.history).mockResolvedValue({
      items: [{ ...ringing, state: 'ended_pending_documentation' }],
      next_cursor: null,
    });
    const w = await factory(['calls.view', 'calls.document']);
    expect(w.find('.ac__docreq').exists()).toBe(true);
    const save = vi.spyOn(tel.telephonyApi, 'putDoc').mockResolvedValue({
      call_id: 'call-1',
      category: 'technical_fault',
      free_text: null,
      documented_by: 'u1',
      documented_at: '',
      mandatory_done: true,
    });
    await w.findAll('input[name="callcat"]')[1].setValue();
    await w.get('.ac__doc').trigger('submit');
    expect(save).toHaveBeenCalledWith('call-1', expect.objectContaining({ category: 'technical_fault' }));
  });

  it('shows a live call duration once connected, as mm:ss (#221)', async () => {
    const startedAt = new Date(Date.now() - 5000).toISOString();
    vi.mocked(tel.telephonyApi.history).mockResolvedValue({
      items: [{ ...ringing, state: 'connected', started_at: startedAt }],
      next_cursor: null,
    });
    const w = await factory(['calls.view']);
    expect(w.find('.ac__duration').text()).toMatch(/^\d+:\d{2}$/);
  });

  it('gates hangup on missing documentation: opens the popup, saves the category, then hangs up (#223)', async () => {
    vi.mocked(tel.telephonyApi.history).mockResolvedValue({
      items: [{ ...ringing, id: 'call-2', state: 'connected' }],
      next_cursor: null,
    });
    const putDoc = vi.spyOn(tel.telephonyApi, 'putDoc').mockResolvedValue({
      call_id: 'call-2',
      category: 'technical_fault',
      free_text: null,
      documented_by: 'u1',
      documented_at: '',
      mandatory_done: true,
    });
    const hangup = vi
      .spyOn(tel.telephonyApi, 'hangup')
      .mockResolvedValue({ call_id: 'call-2', action: 'hangup', accepted: true, detail: 'closed' });
    const w = await factory(['calls.view', 'calls.hangup', 'calls.document']);

    await w.get('.ac__hangup').trigger('click');
    expect(hangup).not.toHaveBeenCalled();
    expect(w.find('.cdd__form').exists()).toBe(true);

    await w.findAll('input[name="cdd-cat"]')[1].setValue();
    await w.get('.cdd__form').trigger('submit');
    await new Promise((r) => setTimeout(r, 0));
    await w.vm.$nextTick();

    expect(putDoc).toHaveBeenCalledWith(
      'call-2',
      expect.objectContaining({ category: 'technical_fault' }),
    );
    expect(hangup).toHaveBeenCalledWith('call-2');
  });

  it('hangs up immediately when documentation is already complete', async () => {
    vi.mocked(tel.telephonyApi.getDoc).mockResolvedValue({
      call_id: 'call-1',
      category: 'other',
      free_text: null,
      documented_by: 'u1',
      documented_at: '',
      mandatory_done: true,
    });
    vi.mocked(tel.telephonyApi.history).mockResolvedValue({
      items: [{ ...ringing, state: 'connected' }],
      next_cursor: null,
    });
    const hangup = vi
      .spyOn(tel.telephonyApi, 'hangup')
      .mockResolvedValue({ call_id: 'call-1', action: 'hangup', accepted: true, detail: 'closed' });
    const w = await factory(['calls.view', 'calls.hangup']);

    await w.get('.ac__hangup').trigger('click');
    expect(hangup).toHaveBeenCalledWith('call-1');
  });
});
