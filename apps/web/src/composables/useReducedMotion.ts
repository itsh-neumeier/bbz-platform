import { onMounted, onUnmounted, ref } from 'vue';
import { prefersReducedMotion } from '@/a11y/reducedMotion';

/**
 * Reactive `prefers-reduced-motion` (E07-07 / #105). Components gate their
 * animations on `reduced.value`; the CSS in `theme/tokens.css` is the belt to
 * this braces.
 */
export function useReducedMotion() {
  const reduced = ref(prefersReducedMotion());

  let mq: MediaQueryList | undefined;
  const onChange = (e: MediaQueryListEvent) => (reduced.value = e.matches);

  onMounted(() => {
    if (typeof window === 'undefined' || !window.matchMedia) return;
    mq = window.matchMedia('(prefers-reduced-motion: reduce)');
    reduced.value = mq.matches;
    mq.addEventListener('change', onChange);
  });
  onUnmounted(() => mq?.removeEventListener('change', onChange));

  return { reduced };
}
