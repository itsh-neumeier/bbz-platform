import { describe, expect, it } from 'vitest';
import { mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import de from '@/i18n/de.json';
import CallDocRequiredDialog from '@/components/telephony/CallDocRequiredDialog.vue';

const i18n = createI18n({ legacy: false, locale: 'de', messages: { de } });

function factory(open: boolean, busy = false) {
  return mount(CallDocRequiredDialog, {
    props: { open, busy },
    global: { plugins: [i18n] },
  });
}

describe('CallDocRequiredDialog (E11-14 / #223)', () => {
  it('disables confirm until a category is chosen', async () => {
    const w = factory(true);
    const confirmBtn = w.find('.cdd__confirm');
    expect(confirmBtn.attributes('disabled')).toBeDefined();

    await w.findAll('input[name="cdd-cat"]')[0].setValue();
    expect(confirmBtn.attributes('disabled')).toBeUndefined();
  });

  it('emits confirm with the chosen category and free text', async () => {
    const w = factory(true);
    await w.findAll('input[name="cdd-cat"]')[2].setValue();
    await w.find('#cdd-free').setValue('Rückruf erbeten');
    await w.find('.cdd__form').trigger('submit');

    const emitted = w.emitted('confirm');
    expect(emitted).toHaveLength(1);
    expect(emitted![0][1]).toBe('Rückruf erbeten');
  });

  it('emits close on cancel without requiring a category', async () => {
    const w = factory(true);
    await w.find('.cdd__cancel').trigger('click');
    expect(w.emitted('close')).toHaveLength(1);
    expect(w.emitted('confirm')).toBeUndefined();
  });

  it('resets the form each time it reopens', async () => {
    const w = factory(true);
    await w.findAll('input[name="cdd-cat"]')[0].setValue();
    await w.find('#cdd-free').setValue('etwas Text');

    await w.setProps({ open: false });
    await w.setProps({ open: true });

    const checked = w.findAll('input[name="cdd-cat"]').filter((i) => (i.element as HTMLInputElement).checked);
    expect(checked).toHaveLength(0);
    expect((w.find('#cdd-free').element as HTMLTextAreaElement).value).toBe('');
  });
});
