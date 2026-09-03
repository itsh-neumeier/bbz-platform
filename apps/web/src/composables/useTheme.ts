import { onMounted, ref, watch } from 'vue';

/**
 * Theme selection (E07-17 / #125). `system` follows `prefers-color-scheme`;
 * `light` / `dark` force it via `data-theme` on `<html>` (the CSS in
 * `theme/tokens.css` makes an explicit choice win in both directions). The
 * choice persists per browser.
 */
export type ThemeChoice = 'system' | 'light' | 'dark';

const KEY = 'bbz.theme';
const choice = ref<ThemeChoice>(readStored());

function readStored(): ThemeChoice {
  try {
    const v = localStorage.getItem(KEY);
    return v === 'light' || v === 'dark' ? v : 'system';
  } catch {
    return 'system';
  }
}

function apply(c: ThemeChoice): void {
  const root = document.documentElement;
  if (c === 'system') root.removeAttribute('data-theme');
  else root.setAttribute('data-theme', c);
}

export function useTheme() {
  onMounted(() => apply(choice.value));

  watch(choice, (c) => {
    apply(c);
    try {
      if (c === 'system') localStorage.removeItem(KEY);
      else localStorage.setItem(KEY, c);
    } catch {
      /* private mode — the in-memory choice still holds for this session */
    }
  });

  function setTheme(c: ThemeChoice): void {
    choice.value = c;
  }

  function cycle(): void {
    choice.value =
      choice.value === 'system' ? 'light' : choice.value === 'light' ? 'dark' : 'system';
  }

  return { theme: choice, setTheme, cycle };
}
