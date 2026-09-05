import { afterEach, describe, expect, it, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { createI18n } from 'vue-i18n';
import de from '@/i18n/de.json';
import RadarTimeline from '@/components/weather/RadarTimeline.vue';
import type { RadarFrame } from '@/lib/weather';

const i18n = createI18n({ legacy: false, locale: 'de', messages: { de } });

const FRAMES: RadarFrame[] = [
  { frame_time: '2026-09-05T10:00:00Z', image_ref: 'https://dwd/radar?t=1' },
  { frame_time: '2026-09-05T10:05:00Z', image_ref: 'https://dwd/radar?t=2' },
  { frame_time: '2026-09-05T10:10:00Z', image_ref: 'https://dwd/radar?t=3' },
];

function factory(frames: RadarFrame[]) {
  return mount(RadarTimeline, { props: { frames }, global: { plugins: [i18n] } });
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe('RadarTimeline (E18-09 / #391)', () => {
  it('starts on the newest frame and shows the position', () => {
    const w = factory(FRAMES);
    expect(w.get('.rt__img').attributes('src')).toBe('https://dwd/radar?t=3');
    expect(w.get('.rt__pos').text()).toBe('Bild 3 von 3');
  });

  it('scrubs to another frame with the range slider (keyboard-operable)', async () => {
    const w = factory(FRAMES);
    const scrub = w.get('.rt__scrub');
    expect(scrub.attributes('aria-label')).toBeTruthy();
    await scrub.setValue('0');
    expect(w.get('.rt__img').attributes('src')).toBe('https://dwd/radar?t=1');
    expect(w.get('.rt__pos').text()).toBe('Bild 1 von 3');
  });

  it('plays through the frames on a timer and wraps, then pauses', async () => {
    vi.useFakeTimers();
    const w = factory(FRAMES);
    await w.get('.rt__play').trigger('click');
    expect(w.get('.rt__play').text()).toBe('Pause');

    vi.advanceTimersByTime(800);
    await w.vm.$nextTick();
    expect(w.get('.rt__img').attributes('src')).toBe('https://dwd/radar?t=1'); // 3 → wrap → 1

    vi.advanceTimersByTime(800);
    await w.vm.$nextTick();
    expect(w.get('.rt__img').attributes('src')).toBe('https://dwd/radar?t=2');

    await w.get('.rt__play').trigger('click');
    expect(w.get('.rt__play').text()).toBe('Abspielen');
    vi.advanceTimersByTime(2400);
    await w.vm.$nextTick();
    expect(w.get('.rt__img').attributes('src')).toBe('https://dwd/radar?t=2'); // frozen
  });

  it('hides the play button under prefers-reduced-motion but keeps the scrubber', () => {
    vi.stubGlobal('matchMedia', () => ({
      matches: true,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
    }));
    const w = factory(FRAMES);
    expect(w.find('.rt__play').exists()).toBe(false);
    expect(w.find('.rt__scrub').exists()).toBe(true);
  });

  it('shows an empty message when there are no frames', () => {
    const w = factory([]);
    expect(w.find('.rt').exists()).toBe(false);
    expect(w.get('.wx__empty').text()).toBe('Kein Radarbild verfügbar.');
  });

  it('offers no play button for a single frame', () => {
    const w = factory([FRAMES[0]]);
    expect(w.find('.rt__play').exists()).toBe(false);
  });
});
