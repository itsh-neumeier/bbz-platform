import { api } from '@/lib/apiClient';

/** Contacts / phone-book API (E14-02/03/06). Personally identifiable — every
 *  call is `contacts.*`-gated server-side. */

export type ContactPriority = 'low' | 'medium' | 'high';

export interface ContactNumber {
  id: string;
  e164: string;
  label: string | null;
  is_primary: boolean;
}

export interface Contact {
  id: string;
  name: string;
  org: string | null;
  notes: string | null;
  quick_dial: boolean;
  bbz_id: string | null;
  priority: ContactPriority | null;
  created_at: string;
  updated_at: string;
  numbers: ContactNumber[];
}

export interface ContactPage {
  items: Contact[];
  next_cursor: string | null;
}

export interface NewContact {
  name: string;
  org?: string | null;
  notes?: string | null;
  quick_dial?: boolean;
  numbers?: { e164: string; label?: string | null; is_primary?: boolean }[];
}

export interface ContactPatch {
  name?: string;
  org?: string | null;
  notes?: string | null;
  quick_dial?: boolean;
}

/** blue / orange / red in the mockup (§13.9) — map priority to a token class. */
export const PRIORITY_CLASS: Record<ContactPriority, string> = {
  low: 'prio--low',
  medium: 'prio--medium',
  high: 'prio--high',
};

export const contactsApi = {
  search: (params: { q?: string; quickDial?: boolean; cursor?: string; limit?: number } = {}) => {
    const qs = new URLSearchParams();
    if (params.q) qs.set('q', params.q);
    if (params.quickDial !== undefined) qs.set('quick_dial', String(params.quickDial));
    if (params.cursor) qs.set('cursor', params.cursor);
    if (params.limit) qs.set('limit', String(params.limit));
    const tail = qs.toString();
    return api.get<ContactPage>(`/contacts${tail ? `?${tail}` : ''}`);
  },

  get: (id: string) => api.get<Contact>(`/contacts/${id}`),

  create: (body: NewContact) => api.post<Contact>('/contacts', body),

  update: (id: string, body: ContactPatch) => api.patch<Contact>(`/contacts/${id}`, body),

  remove: (id: string) => api.del(`/contacts/${id}`),

  setPriority: (id: string, priority: ContactPriority) =>
    api.put<{ contact_id: string; priority: ContactPriority; changed: boolean }>(
      `/contacts/${id}/priority`,
      { priority },
    ),

  addNumber: (id: string, body: { e164: string; label?: string | null; is_primary?: boolean }) =>
    api.post<ContactNumber>(`/contacts/${id}/numbers`, body),

  removeNumber: (id: string, numberId: string) =>
    api.del(`/contacts/${id}/numbers/${numberId}`),
};
