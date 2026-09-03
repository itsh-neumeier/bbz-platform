import { beforeEach, describe, expect, it, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import { createPinia, setActivePinia } from 'pinia';
import de from '@/i18n/de.json';
import PhonebookPage from '@/pages/PhonebookPage.vue';
import { useSessionStore } from '@/stores/session';
import * as contacts from '@/lib/contacts';

const CONTACTS: contacts.Contact[] = [
  {
    id: 'c1',
    name: 'Feuerwehr Nürnberg',
    org: 'BF',
    notes: null,
    quick_dial: true,
    bbz_id: null,
    priority: 'high',
    created_at: '2026-09-01T08:00:00Z',
    updated_at: '2026-09-01T08:00:00Z',
    numbers: [{ id: 'n1', e164: '+4991122233', label: null, is_primary: true }],
  },
  {
    id: 'c2',
    name: 'Stadtwerke',
    org: null,
    notes: null,
    quick_dial: false,
    bbz_id: null,
    priority: null,
    created_at: '2026-09-01T08:00:00Z',
    updated_at: '2026-09-01T08:00:00Z',
    numbers: [],
  },
];

function withPerms(...perms: string[]) {
  const s = useSessionStore();
  s.user = { id: 'u1', display_name: 'Op', status: 'active' };
  s.permissions = perms;
}

beforeEach(() => {
  setActivePinia(createPinia());
  vi.restoreAllMocks();
  vi.spyOn(contacts.contactsApi, 'search').mockResolvedValue({ items: CONTACTS, next_cursor: null });
});

async function factory() {
  const i18n = createI18n({ legacy: false, locale: 'de', messages: { de } });
  const w = mount(PhonebookPage, { global: { plugins: [i18n] } });
  await new Promise((r) => setTimeout(r, 0));
  await w.vm.$nextTick();
  return w;
}

describe('PhonebookPage', () => {
  it('lists contacts with a priority dot and quick-dial star', async () => {
    withPerms('contacts.view');
    const w = await factory();
    const rows = w.findAll('.pb__row');
    expect(rows).toHaveLength(2);
    expect(rows[0].text()).toContain('Feuerwehr Nürnberg');
    expect(rows[0].find('.pb__prio.prio--high').exists()).toBe(true);
    expect(rows[0].find('.pb__star').exists()).toBe(true);
    expect(rows[0].text()).toContain('+4991122233');
  });

  it('opens a detail panel and saves edited fields', async () => {
    withPerms('contacts.view', 'contacts.edit');
    const update = vi
      .spyOn(contacts.contactsApi, 'update')
      .mockResolvedValue({ ...CONTACTS[0], org: 'Berufsfeuerwehr' });
    vi.spyOn(contacts.contactsApi, 'get').mockResolvedValue({ ...CONTACTS[0], org: 'Berufsfeuerwehr' });
    const w = await factory();
    await w.findAll('.pb__row')[0].trigger('click');
    const org = w.get('#pb-e-org');
    await org.setValue('Berufsfeuerwehr');
    await w.get('.pb__detail fieldset button').trigger('click');
    expect(update).toHaveBeenCalledWith('c1', expect.objectContaining({ org: 'Berufsfeuerwehr' }));
  });

  it('assigns a priority', async () => {
    withPerms('contacts.view', 'contacts.assign_priority');
    const setPriority = vi
      .spyOn(contacts.contactsApi, 'setPriority')
      .mockResolvedValue({ contact_id: 'c2', priority: 'medium', changed: true });
    vi.spyOn(contacts.contactsApi, 'get').mockResolvedValue({ ...CONTACTS[1], priority: 'medium' });
    const w = await factory();
    await w.findAll('.pb__row')[1].trigger('click');
    const btns = w.findAll('.pb__prio-btn');
    await btns[1].trigger('click');
    expect(setPriority).toHaveBeenCalledWith('c2', 'medium');
  });

  it('hides create / edit / delete controls without the permission', async () => {
    withPerms('contacts.view');
    const w = await factory();
    expect(w.find('.pb__new').exists()).toBe(false);
    await w.findAll('.pb__row')[0].trigger('click');
    expect(w.find('.pb__delete').exists()).toBe(false);
    // the stammdaten fieldset is disabled
    expect(w.get('.pb__detail fieldset').attributes('disabled')).toBeDefined();
  });

  it('creates a contact', async () => {
    withPerms('contacts.view', 'contacts.create');
    const create = vi
      .spyOn(contacts.contactsApi, 'create')
      .mockResolvedValue({ ...CONTACTS[1], id: 'c3', name: 'Neuer' });
    const w = await factory();
    await w.get('.pb__new').trigger('click');
    await w.get('#pb-n-name').setValue('Neuer');
    await w.get('.pb__create').trigger('submit');
    expect(create).toHaveBeenCalledWith(expect.objectContaining({ name: 'Neuer' }));
  });
});
