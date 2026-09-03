# DB UX Design System integration

The BBZ web frontend is visually based on the **DB UX Design System v3**
(`github.com/db-ux-design-system/core-web`). Decision + rationale: **ADR-0029**
(extends ADR-0013).

## Why a token layer, not components

The BBZ UI uses **no PrimeVue components** — it is semantic HTML (`<button>`,
`<select>`, `<table>`, `<dialog>`, `<fieldset>`) with scoped CSS driven entirely
by `--bbz-*` CSS custom properties. So the design system is adopted as a **token
+ typography foundation**, and `@db-ux/core-components` / `v-core-components` are
**not** used (they would duplicate every control the app already has and add a
second component model beside PrimeVue). PrimeVue stays registered per ADR-0013
with a DB-flavoured preset (`theme/primevue-db-preset.ts`) so a future PrimeVue
component inherits DB styling.

## Architecture

```
DB UX Design System v3
  @db-ux/core-foundations@5.3.0   tokens, scales, adaptive light-dark(), reset
  @db-ux/db-theme@6.2.0           the Deutsche Bahn palette (values only)
        │
        ▼   src/theme/db.css        →  @layer db-tokens, db-ux
src/theme/db-brand.css              DB palette override (from @db-ux/db-theme)
src/theme/semantic-tokens.css       --bbz-* = var(--db-*)   →  @layer bbz
src/theme/typography.css            DB type scale, control-room sizing
src/theme/fonts.css                 DB Screen Sans @font-face (licensed)
src/theme/components.css            baseline <button>/input/table/dialog styling
        │
        ▼   Vue scoped <style>       unlayered → always wins
BBZ components
```

`@layer db-tokens, db-ux, bbz;` — the DB framework CSS (which carries an
opinionated element reset) sits in the lowest layers; the BBZ layer sits above;
Vue scoped styles are unlayered and beat everything, so no component can be
broken by the framework.

### Files

| file | purpose |
|---|---|
| `theme/index.css` | entry — imports the parts in order + the global `prefers-reduced-motion` rule |
| `theme/db.css` | imports `@db-ux/core-foundations` `theme/rollup.css` + `bundle.css` into layers |
| `theme/db-brand.css` | the DB palette (`--db-brand-*`, `--db-neutral-*`, `--db-informational/successful/warning/critical-*`, `--db-brand-origin-*`) transcribed from `@db-ux/db-theme` |
| `theme/semantic-tokens.css` | every `--bbz-*` token as a reference into the DB set; the `data-mode` colour-scheme switch (unlayered) |
| `theme/typography.css` | `--bbz-font-*`, the type scale, `h1..h4` sizing for a dense ops UI |
| `theme/fonts.css` | `@font-face` for DB Screen Sans / Head / Digital |
| `theme/components.css` | DB defaults for the plain HTML the app uses |
| `theme/primevue-db-preset.ts` | `definePreset(Aura, …)` mapping PrimeVue tokens onto `--db-*` |
| `theme/legacy-tokens.css` | the pre-ADR-0029 `tokens.css`, kept for rollback |

## Dark / light mode

DB v3 resolves light/dark through the CSS `light-dark()` function against
`color-scheme`. `useTheme` writes, on `<html>`:

- `data-theme` — legacy BBZ hook (kept)
- `data-mode` (`light` / `dark`; absent = system)
- inline `color-scheme` — belt to the `html[data-mode] { color-scheme }` rule,
  so nothing in the cascade disagrees

`system` (no attributes) follows `prefers-color-scheme`, seeded by
`<meta name="color-scheme" content="light dark">` in `index.html`.

Requires Chromium ≥ 123 / Safari ≥ 17.5 / Firefox ≥ 120 (`light-dark()`). The
BBZ kiosk is a current Chromium/Electron build.

## Colours

| BBZ token | DB source |
|---|---|
| `--bbz-accent` / `--bbz-db-red` | `--db-adaptive-origin` / `--db-brand-origin-base` (`#ec0016`) |
| `--bbz-bg` / `--bbz-surface` / `--bbz-surface-alt` | `--db-adaptive-bg-basic-level-1/2/3` |
| `--bbz-text` / `--bbz-text-muted` | `--db-adaptive-on-bg-basic-emphasis-100/70` |
| `--bbz-border` | `--db-adaptive-on-bg-basic-emphasis-50` |
| `--bbz-info` / `--bbz-success` / `--bbz-warn` / `--bbz-danger` | `--db-informational-7` / `--db-successful-7` / `--db-warning-7` / `--db-critical-8` |
| `--bbz-prio-low` / `-medium` / `-high` / `-critical` | `--db-informational-7` / `--db-warning-8` / `--db-critical-8` / `--db-critical-10` |

The four **BBZ alarm / contact priorities** (MASTER_PROMPT §13.3, §13.9 —
niedrig blau / mittel orange / hoch rot / kritisch tiefrot) keep their meaning,
re-pointed at the DB semantic ramps, and are always shown with a label or icon —
never colour alone.

**No hand-picked hex** in `semantic-tokens.css` (enforced by `theme.spec.ts`).

## Licensed assets (not in the repo)

`.gitignore`d — place on each build/deploy host:

| asset | location | fallback if absent |
|---|---|---|
| **DB Screen Sans** (DB Type 2.5, WEB `.woff2`) | `apps/web/public/fonts/db-screen-sans/` | `--db-font-family-sans` (helvetica / arial) → system |
| **DB logo** (SVG) | `apps/web/public/brand/db-logo.svg` | the "DB" wordmark on DB red |

See the `README.md` in each directory. Newer **DB Neo Screen Sans** (v3) + the
logo can also come from `@db-ux/db-theme`'s `postinstall` with the DB
Marketingportal `ASSET_PASSWORD` / `ASSET_INIT_VECTOR`.

## Rollback

`main.ts` imports `./theme/index.css`. Reverting the DB-UX PR, or pointing that
import at `./theme/legacy-tokens.css` and restoring the `Aura` preset in
`main.ts`, returns the previous appearance with no data / API impact.

## Regenerating `db-brand.css`

```sh
mkdir /tmp/dbt && cd /tmp/dbt && npm init -y -s
npm i @db-ux/db-theme@<version>
node -e '
const fs=require("fs");
const s=fs.readFileSync("node_modules/@db-ux/db-theme/build/styles/rollup.css","utf8");
const re=/@property\s+(--db-[\w-]+)\s*\{([^}]*)\}/g; let m;
while((m=re.exec(s))){const v=/initial-value:\s*(#[0-9a-fA-F]{3,8})/.exec(m[2]);
 if(v && m[2].includes("<color>")) console.log(`  ${m[1]}: ${v[1]};`);}'
```

Filter to the `brand`, `neutral`, `informational`, `successful`, `warning`,
`critical`, `blue`, `yellow`, `green`, `red` numbered ramps + `brand-origin-*`.
