import { beforeEach, describe, expect, it } from 'vitest';
import { mount } from '@vue/test-utils';
import { useTheme } from '@/composables/useTheme';

const Host = {
  setup() {
    return useTheme();
  },
  template: '<div />',
};

const root = () => document.documentElement;
const cycle = (w: { vm: unknown }) => (w.vm as { cycle: () => void }).cycle();

beforeEach(() => {
  localStorage.clear();
  root().removeAttribute('data-theme');
  root().removeAttribute('data-mode');
  root().style.removeProperty('color-scheme');
});

describe('useTheme', () => {
  it('defaults to system — no data-theme / data-mode / inline color-scheme', () => {
    mount(Host);
    expect(root().hasAttribute('data-theme')).toBe(false);
    expect(root().hasAttribute('data-mode')).toBe(false);
    expect(root().style.getPropertyValue('color-scheme')).toBe('');
  });

  it('cycles system → light → dark → system, writing data-theme + data-mode (ADR-0029)', async () => {
    const w = mount(Host);

    cycle(w);
    await w.vm.$nextTick();
    expect(root().getAttribute('data-theme')).toBe('light');
    expect(root().getAttribute('data-mode')).toBe('light');
    expect(localStorage.getItem('bbz.theme')).toBe('light');

    cycle(w);
    await w.vm.$nextTick();
    expect(root().getAttribute('data-theme')).toBe('dark');
    expect(root().getAttribute('data-mode')).toBe('dark');

    cycle(w);
    await w.vm.$nextTick();
    expect(root().hasAttribute('data-theme')).toBe(false);
    expect(root().hasAttribute('data-mode')).toBe(false);
    expect(localStorage.getItem('bbz.theme')).toBeNull();
  });
});
