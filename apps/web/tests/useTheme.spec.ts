import { beforeEach, describe, expect, it } from 'vitest';
import { mount } from '@vue/test-utils';
import { useTheme } from '@/composables/useTheme';

const Host = {
  setup() {
    return useTheme();
  },
  template: '<div />',
};

beforeEach(() => {
  localStorage.clear();
  document.documentElement.removeAttribute('data-theme');
});

describe('useTheme', () => {
  it('defaults to system (no data-theme attribute)', () => {
    mount(Host);
    expect(document.documentElement.hasAttribute('data-theme')).toBe(false);
  });

  it('cycles system → light → dark → system and persists', async () => {
    const w = mount(Host);
    (w.vm as unknown as { cycle: () => void }).cycle();
    await w.vm.$nextTick();
    expect(document.documentElement.getAttribute('data-theme')).toBe('light');
    expect(localStorage.getItem('bbz.theme')).toBe('light');

    (w.vm as unknown as { cycle: () => void }).cycle();
    await w.vm.$nextTick();
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');

    (w.vm as unknown as { cycle: () => void }).cycle();
    await w.vm.$nextTick();
    expect(document.documentElement.hasAttribute('data-theme')).toBe(false);
    expect(localStorage.getItem('bbz.theme')).toBeNull();
  });
});
