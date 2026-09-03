import { definePreset } from '@primevue/themes';
import Aura from '@primevue/themes/aura';

/**
 * DB-flavoured PrimeVue preset (ADR-0029).
 *
 * No component uses PrimeVue today, but it stays registered per ADR-0013 /
 * MASTER_PROMPT §6. This preset re-points PrimeVue's primitive + semantic tokens
 * at the DB UX v3 CSS custom properties, so any PrimeVue component added later is
 * DB-styled by default and follows the same light/dark (`data-mode`) switch —
 * without pulling PrimeVue's own colour system.
 */
export const DbPreset = definePreset(Aura, {
  semantic: {
    primary: {
      50: 'var(--db-brand-14)',
      100: 'var(--db-brand-13)',
      200: 'var(--db-brand-12)',
      300: 'var(--db-brand-11)',
      400: 'var(--db-brand-9)',
      500: 'var(--db-brand-origin-base)',
      600: 'var(--db-brand-6)',
      700: 'var(--db-brand-5)',
      800: 'var(--db-brand-4)',
      900: 'var(--db-brand-3)',
      950: 'var(--db-brand-2)',
    },
    focusRing: {
      width: 'var(--db-border-width-xs)',
      style: 'solid',
      color: 'var(--db-focus-outline-color)',
      offset: '2px',
    },
    borderRadius: {
      none: '0',
      xs: 'calc(var(--db-border-radius-xs) / 2)',
      sm: 'var(--db-border-radius-xs)',
      md: 'var(--db-border-radius-xs)',
      lg: 'var(--db-border-radius-xs)',
      xl: 'var(--db-border-radius-xs)',
    },
    colorScheme: {
      light: {
        surface: {
          0: 'var(--db-adaptive-bg-basic-level-1-default)',
          50: 'var(--db-adaptive-bg-basic-level-2-default)',
          100: 'var(--db-adaptive-bg-basic-level-3-default)',
          200: 'var(--db-neutral-11)',
          300: 'var(--db-neutral-10)',
          400: 'var(--db-neutral-9)',
          500: 'var(--db-neutral-8)',
          600: 'var(--db-neutral-6)',
          700: 'var(--db-neutral-4)',
          800: 'var(--db-neutral-2)',
          900: 'var(--db-neutral-1)',
          950: 'var(--db-neutral-0)',
        },
        content: {
          background: 'var(--db-adaptive-bg-basic-level-2-default)',
          hoverBackground: 'var(--db-adaptive-bg-basic-level-3-default)',
        },
        text: {
          color: 'var(--db-adaptive-on-bg-basic-emphasis-100-default)',
          mutedColor: 'var(--db-adaptive-on-bg-basic-emphasis-70-default)',
        },
      },
      dark: {
        surface: {
          0: 'var(--db-adaptive-bg-basic-level-1-default)',
          50: 'var(--db-adaptive-bg-basic-level-2-default)',
          100: 'var(--db-adaptive-bg-basic-level-3-default)',
          200: 'var(--db-neutral-3)',
          300: 'var(--db-neutral-4)',
          400: 'var(--db-neutral-5)',
          500: 'var(--db-neutral-7)',
          600: 'var(--db-neutral-8)',
          700: 'var(--db-neutral-10)',
          800: 'var(--db-neutral-12)',
          900: 'var(--db-neutral-13)',
          950: 'var(--db-neutral-14)',
        },
        content: {
          background: 'var(--db-adaptive-bg-basic-level-2-default)',
          hoverBackground: 'var(--db-adaptive-bg-basic-level-3-default)',
        },
        text: {
          color: 'var(--db-adaptive-on-bg-basic-emphasis-100-default)',
          mutedColor: 'var(--db-adaptive-on-bg-basic-emphasis-70-default)',
        },
      },
    },
  },
});
