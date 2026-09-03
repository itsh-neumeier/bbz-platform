import { beforeEach, describe, expect, it, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import de from '@/i18n/de.json';
import ReactivateDialog from '@/components/events/ReactivateDialog.vue';
import * as ev from '@/lib/events';

// jsdom has no <dialog> methods
beforeEach(() => {
  HTMLDialogElement.prototype.showModal = vi.fn();
  HTMLDialogElement.prototype.close = vi.fn();
  vi.restoreAllMocks();
});

function factory(props: { open: boolean; eventId: string }) {
  const i18n = createI18n({ legacy: false, locale: 'de', messages: { de } });
  return mount(ReactivateDialog, { props, global: { plugins: [i18n] } });
}

const flush = () => new Promise((r) => setTimeout(r, 10));

describe('ReactivateDialog', () => {
  it('fetches an intent token when opened and disables confirm until a reason is typed', async () => {
    const intent = vi
      .spyOn(ev.eventsApi, 'reactivationIntent')
      .mockResolvedValue({ token: 'tok', expires_at: '', event_version: 4 });

    const w = factory({ open: false, eventId: 'e1' });
    await w.setProps({ open: true });
    await flush();

    expect(intent).toHaveBeenCalledWith('e1');
    expect(w.get('.rd__confirm').attributes('disabled')).toBeDefined();

    await w.get('#rd-reason').setValue('Rückfrage');
    await w.vm.$nextTick();
    expect(w.get('.rd__confirm').attributes('disabled')).toBeUndefined();
  });

  it('sends confirm + reason + token + version and emits done', async () => {
    vi.spyOn(ev.eventsApi, 'reactivationIntent').mockResolvedValue({
      token: 'tok',
      expires_at: '',
      event_version: 7,
    });
    const react = vi.spyOn(ev.eventsApi, 'reactivate').mockResolvedValue({} as never);

    const w = factory({ open: true, eventId: 'e9' });
    await flush();
    await flush();
    await w.get('#rd-reason').setValue('Grund X');
    await w.vm.$nextTick();
    expect(w.get('.rd__confirm').attributes('disabled')).toBeUndefined();
    await w.get(".rd__confirm").trigger("click");
    await flush();
    await flush();

    expect(react).toHaveBeenCalledWith('e9', 'tok', 'Grund X', 7);
    expect(w.emitted('done')).toBeTruthy();
  });
});
