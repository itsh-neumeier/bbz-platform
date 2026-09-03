# ADR-0029: DB UX Design System v3 as the visual foundation

## Status
Accepted (2026-09-03, review issue #713) — extends ADR-0013.

## Context

ADR-0013 fixed the frontend stack (Vue 3 / TS strict / PrimeVue 4 (Aura preset) /
Pinia / Vue Router / vue-i18n) and put design tokens in `src/theme/tokens.css`.
MASTER_PROMPT §6 requires "PrimeVue"; §13.2 requires **"DB Branding"** in the
sidebar; the app is a DB InfraGO Personenbahnhöfe control-room tool.

Two facts on the ground as of #713:

1. **No component uses PrimeVue.** The whole UI is semantic HTML (`<button>`,
   `<select>`, `<table>`, `<dialog>`, `<fieldset>`) with scoped CSS driven
   entirely by `--bbz-*` CSS custom properties. `primevue`, `@primevue/themes`
   and `primeicons` are registered in `main.ts` but never consumed.
2. The look is a hand-built neutral palette. `--bbz-db-red: #ec0016` is the only
   DB reference; nothing else is DB-conformant.

Issue #713 asks for a consistent **DB Corporate** appearance across the platform,
with the **DB UX Design System v3** (`github.com/db-ux-design-system/core-web`)
as the technical reference — not the older `db-ui.github.io` (v2).

DB UX v3 ships as npm packages:
- `@db-ux/core-foundations` (5.3.0) — design tokens (`--db-*`), fonts, icons.
- `@db-ux/db-theme` (6.2.0) — the Deutsche Bahn brand palette + logo/assets.
- `@db-ux/db-theme-fonts` — `@font-face` for DB Screen Sans.

The token model: a numbered palette (`--db-brand-0…14`, `--db-neutral-0…14`,
`--db-informational/successful/warning/critical-0…14`), semantic "speaking"
colors (`--db-neutral-bg-basic-level-1-default`, `--db-neutral-on-bg-basic-…`),
and adaptive tokens (`--db-adaptive-bg-basic-level-1`, `--db-adaptive-on-bg-…`)
that resolve light/dark via the CSS `light-dark()` function. Dark mode is a
`color-scheme` / `[data-mode="dark"|"light"]` mechanism, not `prefers-color-scheme`
media queries.

## Decision

**Adopt DB UX v3 as the token + typography foundation; keep PrimeVue registered
with a DB-bridged preset; keep the `--bbz-*` layer as the app's semantic
abstraction.**

```
DB UX Design System v3  (@db-ux/core-foundations + @db-ux/db-theme)
        │  official --db-* tokens, DB palette, DB Screen Sans, light-dark()
        ▼
theme/db.css            imports the DB CSS into  @layer db-ux
        ▼
theme/semantic-tokens.css   --bbz-* defined as references to --db-* / DB palette
theme/typography.css        DB type scale, control-room density
theme/components.css        baseline styling for the plain HTML the app uses
        ▼   @layer bbz
Vue scoped component styles  (unlayered → always win; free to override)
        ▼
BBZ UI
```

- **Layering.** `@layer db-ux, bbz;` — the DB framework CSS (which carries an
  opinionated reset) sits in the lowest layer; the BBZ semantic + component layer
  sits above it; Vue's scoped `<style>` blocks are unlayered and beat both, so no
  component can be broken by the framework and every component keeps full control.
- **Colours.** `--bbz-accent` → DB brand red. Surfaces → `--db-adaptive-bg-basic-
  level-{1,2,3}`. Text → `--db-adaptive-on-bg-basic-emphasis-{100,80,60}`. Border
  → a DB neutral. Semantic success/warning/critical/info → the DB semantic ramps.
  **No hand-picked hex.** The four BBZ priority colours (§13.3 event priority,
  §13.9 contact priority blau/orange/rot) keep their meaning but are re-pointed
  at the DB `informational` (blue) / `warning` (orange) / `critical` (red) ramps,
  with `critical` a deeper red — and every priority is always shown with a label
  or icon, never colour alone.
- **Dark mode.** `useTheme` already writes `data-theme` on `<html>` for the BBZ
  toggle; it now also writes `data-mode` (`light` / `dark`; absent = system) so
  the DB `light-dark()` tokens follow the same control. `<meta name="color-scheme"
  content="light dark">` is added to `index.html`. The legacy
  `@media (prefers-color-scheme: dark)` block is removed — `light-dark()` covers
  system preference once `color-scheme` is set on `:root`.
- **PrimeVue.** Stays registered (ADR-0013, MASTER_PROMPT §6). The `Aura` preset
  is replaced by `definePreset(Aura, …)` in `theme/primevue-db-preset.ts` that
  maps PrimeVue's primary palette / surface / border-radius / focus ring onto the
  DB tokens, so any PrimeVue component added later is DB-styled by default.
  `primeicons` stays for now; DB icons (`@db-ux/db-theme-icons`) are a follow-up.
- **`prefers-reduced-motion`.** The existing global rule is kept.
- **Fonts.** DB Screen Sans (DB Type 2.5, client-licensed woff2) via
  `theme/fonts.css`, `font-display: swap`, with `--db-font-family-sans`
  (DB's own helvetica/arial chain) then a system stack behind it so a missing /
  blocked font never leaves the app unstyled. The files are `.gitignore`d
  (licensed — must not be redistributed via a public repo);
  `@db-ux/db-theme-fonts` is **not** a dependency (its assets are
  license-encrypted). Newer DB Neo Screen Sans (v3) drops in the same way.

### Not adopted (and why)

- **`@db-ux/core-components` / `v-core-components`.** They would duplicate every
  control the app already has and pull a second component model alongside
  PrimeVue. The task explicitly forbids replacing PrimeVue wholesale, and the app
  needs no ready-made components — only the design language. Revisit only if a
  concrete component gap appears.
- **`bundle.css` density / adaptive-container (`data-color`) machinery** beyond
  the token layer. The app maps `--bbz-*` straight onto `--db-adaptive-*`; it
  does not wrap regions in `data-color`/`DBSection`. Keeps the integration flat.
- **`@db-ux/db-theme-fonts`** (all assets `.enc`) and **`@db-ux/core-vite-plugin`**
  (tree-shakes token declarations the `--bbz-*` layer references only through
  `var()`, so it emitted an empty bundle). The DB CSS is imported directly with
  explicit `@layer` assignment instead.

## Consequences

- `apps/web` gains `@db-ux/core-foundations` + `@db-ux/db-theme` (exact-pinned,
  like `primevue`). `@db-ux/db-theme` is imported for the palette **values only**
  (plain CSS) — its logo/font *assets* are license-encrypted and neutralised; the
  `db-brand.css` palette is transcribed with provenance.
- `src/theme/tokens.css` is replaced by a `src/theme/` folder (`db.css`,
  `db-brand.css`, `semantic-tokens.css`, `typography.css`, `fonts.css`,
  `components.css`, `index.css`, `primevue-db-preset.ts`); the old file is kept
  as `src/theme/legacy-tokens.css` for the documented rollback.
- Bundle grows by the DB token CSS (~280 KB uncompressed, mostly `@property`
  declarations + `light-dark()`, small gzipped) + the DB Screen Sans woff2 faces
  when present.
- Licensed assets (DB Screen Sans, the DB logo SVG) live `.gitignore`d under
  `apps/web/public/{fonts/db-screen-sans,brand}/` with a README + a graceful
  fallback; a public clone renders with the fallback.
- `light-dark()` needs Chromium ≥ 123 / Safari ≥ 17.5 / Firefox ≥ 120. The BBZ
  kiosk is a current Chromium/Electron build — fine. jsdom (Vitest) does not
  evaluate `light-dark()`; component tests assert DOM/behaviour, not computed
  colour, and `useTheme.spec.ts` is updated for `data-mode`.
- a11y baseline (ADR-0013) is unchanged: DB tokens are WCAG-checked upstream, the
  `vuejs-accessibility` error-level lint stays, priority is never colour-only.

## Rollback

`main.ts` imports `./theme/index.css` and `DbPreset`. Reverting this PR — or, for
a hot fix, pointing that import at `./theme/legacy-tokens.css` and swapping
`DbPreset` back for `@primevue/themes/aura` — returns the previous appearance
with no data or API impact. Documented in `docs/frontend/db-ux-design.md`.

## Alternatives considered

- **Hand-curate the DB palette into a static CSS file.** Rejected: "keine frei
  erfundenen DB-Farben" — the adaptive/light-dark token chain is deep, and a
  hand copy drifts from the source and misses dark-mode values.
- **Full `@db-ux/core-components` adoption, drop PrimeVue.** Rejected: contradicts
  ADR-0013 / MASTER_PROMPT §6 and the issue's explicit non-goal; large rewrite
  for no functional gain.
- **Only set `--primary-color: #ec0016`.** Rejected by the issue as insufficient.
