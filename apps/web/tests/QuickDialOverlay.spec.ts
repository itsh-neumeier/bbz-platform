import { describe, expect, it, vi } from 'vitest';
import { flushPromises, mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import de from '@/i18n/de.json';
import * as contacts from '@/lib/contacts';
import QuickDialOverlay from '@/components/telephony/QuickDialOverlay.vue';

const i18n = createI18n({ legacy: false, locale: 'de', messages: { de } });

const GATEHOUSE: contacts.Contact = {
  id: 'c1',
  name: 'Pförtner Haupttor',
  org: 'Werkschutz',
  notes: null,
  quick_dial: true,
  bbz_id: null,
  priority: 'medium',
  created_at: '2026-09-01T08:00:00Z',
  updated_at: '2026-09-01T08:00:00Z',
  numbers: [{ id: 'n1', e164: '+498955501', label: null, is_primary: true }],
};

const NO_NUMBER: contacts.Contact = {
  ...GATEHOUSE,
  id: 'c2',
  name: 'Ohne Nummer',
  numbers: [],
};

async function factory(open: boolean) {
  const w = mount(QuickDialOverlay, {
    props: { open },
    global: { plugins: [i18n] },
  });
  await flushPromises();
  return w;
}

describe('QuickDialOverlay (E11-15 / #225)', () => {
  it('loads and lists the quick-dial contacts once opened', async () => {
    vi.spyOn(contacts.contactsApi, 'search').mockResolvedValue({
      items: [GATEHOUSE],
      next_cursor: null,
    });
    const w = await factory(true);

    expect(contacts.contactsApi.search).toHaveBeenCalledWith(
      expect.objectContaining({ quickDial: true }),
    );
    const item = w.find('.qd__item');
    expect(item.text()).toContain('Pförtner Haupttor');
    expect(item.text()).toContain('+498955501');
  });

  it('emits dial with the chosen contact', async () => {
    vi.spyOn(contacts.contactsApi, 'search').mockResolvedValue({
      items: [GATEHOUSE],
      next_cursor: null,
    });
    const w = await factory(true);

    await w.find('.qd__item').trigger('click');

    const emitted = w.emitted('dial');
    expect(emitted).toHaveLength(1);
    expect(emitted![0][0]).toEqual(GATEHOUSE);
  });

  it('disables a contact with no number and never emits dial for it', async () => {
    vi.spyOn(contacts.contactsApi, 'search').mockResolvedValue({
      items: [NO_NUMBER],
      next_cursor: null,
    });
    const w = await factory(true);

    const item = w.find('.qd__item');
    expect(item.attributes('disabled')).toBeDefined();
    await item.trigger('click');
    expect(w.emitted('dial')).toBeUndefined();
  });

  it('shows an empty message when there are no quick-dial contacts', async () => {
    vi.spyOn(contacts.contactsApi, 'search').mockResolvedValue({
      items: [],
      next_cursor: null,
    });
    const w = await factory(true);

    expect(w.find('.qd__muted').exists()).toBe(true);
    expect(w.find('.qd__item').exists()).toBe(false);
  });

  it('emits close on cancel', async () => {
    vi.spyOn(contacts.contactsApi, 'search').mockResolvedValue({
      items: [GATEHOUSE],
      next_cursor: null,
    });
    const w = await factory(true);

    await w.find('.qd__cancel').trigger('click');
    expect(w.emitted('close')).toHaveLength(1);
  });
});
