import { onMounted, ref, watch } from 'vue';

/**
 * Theme selection (E07-17 / #125, ADR-0029). `system` follows
 * `prefers-color-scheme`; `light` / `dark` force it. Two attributes are written
 * on `<html>`: `data-theme` (legacy BBZ CSS) and `data-mode` (DB UX v3 —
 * `[data-mode]` sets `color-scheme`, which is what the DB `light-dark()` tokens
 * resolve against). `system` = neither attribute set. The choice persists per
 * browser.
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
  if (c === 'system') {
    root.removeAttribute('data-theme');
    root.removeAttribute('data-mode');
    root.style.removeProperty('color-scheme');
  } else {
    root.setAttribute('data-theme', c);
    root.setAttribute('data-mode', c);
    // inline `color-scheme` is what the DB `light-dark()` tokens resolve against
    // — set it directly so nothing in the cascade can disagree (ADR-0029).
    root.style.setProperty('color-scheme', c);
  }
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
