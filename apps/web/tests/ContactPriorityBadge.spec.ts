import { describe, expect, it } from 'vitest';
import { mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import de from '@/i18n/de.json';
import ContactPriorityBadge from '@/components/telephony/ContactPriorityBadge.vue';
import type { ContactPriority } from '@/lib/contacts';

const i18n = createI18n({ legacy: false, locale: 'de', messages: { de } });

function mountBadge(priority: ContactPriority) {
  return mount(ContactPriorityBadge, { props: { priority }, global: { plugins: [i18n] } });
}

describe('ContactPriorityBadge (E14-08 / #299)', () => {
  it.each([
    ['low', 'niedrig'],
    ['medium', 'mittel'],
    ['high', 'hoch'],
  ] as const)('renders %s as a text badge reading "%s" (not colour-only)', (priority, label) => {
    const w = mountBadge(priority);
    expect(w.text()).toBe(label);
    expect(w.classes()).toContain(`cpb--${priority}`);
  });
});
