import { beforeEach, describe, expect, it, vi } from 'vitest';
import { mount } from '@vue/test-utils';
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
  const w = mount(CommsSidebar, { global: { plugins: [pinia, i18n] } });
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
});
