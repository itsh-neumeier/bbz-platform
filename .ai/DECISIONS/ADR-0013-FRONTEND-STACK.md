# ADR-0013: Frontend Stack and Accessibility Baseline

## Status
Proposed

## Context
MASTER_PROMPT §6/§13 fix Vue 3 + PrimeVue + Pinia + Vue Router + i18n and treat
the functional mockup as the binding UX/feature reference. Accessibility is a
functional requirement (`.ai/RULES.md`).

## Decision
- Vite + Vue 3 + TypeScript (strict) + PrimeVue 4 (Aura theme preset) + Pinia +
  Vue Router + vue-i18n (DE launch locale).
- Design tokens in `src/theme/tokens.css`; light/dark via `prefers-color-scheme`
  and an explicit `data-theme` override; global `prefers-reduced-motion` rule.
- ESLint flat config with `eslint-plugin-vue` + `eslint-plugin-vuejs-accessibility`
  at **error** level in CI.
- Tests: Vitest (unit/component, jsdom) + Playwright (E2E). The mandatory E2E
  scripts from §24/§35/§36.1 are implemented with the features they cover.
- Every operable control has a non-drag, keyboard-reachable path (sidebar resize,
  monitor routing, EPK editor).
- The web build stays runnable in a plain browser; Electron only embeds it.

## Consequences
- a11y regressions fail the build.
- Mockup parity is tracked explicitly (checklist in `docs/`), not assumed.

## Alternatives considered
React/other component kits (rejected: MASTER_PROMPT fixes Vue/PrimeVue);
Vuetify/Quasar (rejected: PrimeVue is specified).
