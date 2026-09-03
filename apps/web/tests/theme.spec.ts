import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { describe, expect, it } from 'vitest';

// vitest runs with cwd = apps/web
const raw = (rel: string) => readFileSync(join(process.cwd(), 'src/theme', rel), 'utf8');
/** file contents with block comments stripped */
const code = (rel: string) => raw(rel).replace(/\/\*[\s\S]*?\*\//g, '');

describe('DB UX theme (ADR-0029)', () => {
  it('layers the DB framework below the bbz layer', () => {
    const db = code('db.css');
    expect(db).toMatch(/@layer\s+db-tokens\s*,\s*db-ux\s*,\s*bbz\s*;/);
    expect(db).toContain(
      "@db-ux/core-foundations/build/styles/theme/rollup.css' layer(db-tokens)",
    );
    expect(db).toContain("@db-ux/core-foundations/build/styles/bundle.css' layer(db-ux)");
  });

  it('carries the Deutsche Bahn brand red from @db-ux/db-theme', () => {
    const brand = code('db-brand.css');
    expect(brand).toMatch(/--db-brand-origin-base:\s*#ec0016/);
    expect(brand).toMatch(/--db-brand-7:\s*#ef0016/);
    expect(brand).toMatch(/--db-neutral-0:\s*#0d0e11/);
    expect(brand).toMatch(/--db-neutral-14:\s*#ffffff/);
  });

  it('carries the DB semantic origin colours (vivid, mode-independent)', () => {
    const brand = code('db-brand.css');
    // the numbered ramps run dark -> light; status fills use the "origin" value
    expect(brand).toMatch(/--db-critical-origin-base:\s*#ec0016/);
    expect(brand).toMatch(/--db-warning-origin-base:\s*#f39200/);
    expect(brand).toMatch(/--db-successful-origin-base:\s*#63a615/);
    expect(brand).toMatch(/--db-informational-origin-base:\s*#309fd1/);
  });

  it('defines every --bbz-* colour token as a reference into the DB set', () => {
    const sem = code('semantic-tokens.css');
    const decls = [...sem.matchAll(/(--bbz-[\w-]+)\s*:\s*([^;]+);/g)];
    expect(decls.length).toBeGreaterThan(20);
    const rawHex = decls
      .filter(([, , value]) => /#[0-9a-f]{3,8}/i.test(value))
      .map(([, name]) => name);
    expect(rawHex).toEqual([]);
    // §13.9 priority meaning preserved, re-pointed at the DB semantic origins
    expect(sem).toMatch(/--bbz-prio-low:\s*var\(--db-informational-origin/);
    expect(sem).toMatch(/--bbz-prio-medium:\s*var\(--db-warning-origin/);
    expect(sem).toMatch(/--bbz-prio-high:\s*var\(--db-critical-origin/);
    // kritisch is a deeper red than hoch so it still outranks it by colour
    expect(sem).toMatch(/--bbz-prio-critical:\s*var\(--db-critical-6\)/);
    // every priority fill has an explicit on-colour for text contrast
    for (const p of ['low', 'medium', 'high', 'critical']) {
      expect(sem).toMatch(new RegExp(`--bbz-on-prio-${p}:\\s*var\\(--db-`));
    }
    // the interactive accent is the DB brand, not the (neutral) adaptive origin
    expect(sem).toMatch(/--bbz-accent:\s*var\(--db-brand-origin-base\)/);
    expect(sem).not.toMatch(/--bbz-accent:\s*var\(--db-adaptive-origin\)/);
    // the focus colour carries DB's own fallback (the custom prop is opt-in)
    expect(sem).toMatch(/--bbz-focus-color:\s*var\(\s*--db-focus-outline-color\s*,/);
    // green connects, red ends — telephony keeps its convention
    expect(sem).toMatch(/--bbz-call:\s*var\(--db-successful/);
  });

  it('switches colour scheme on data-mode, unlayered so it always wins', () => {
    const sem = raw('semantic-tokens.css');
    expect(sem).toMatch(/html\[data-mode='dark'\]\s*\{\s*color-scheme:\s*dark;\s*\}/);
    expect(sem).toMatch(/html\[data-mode='light'\]\s*\{\s*color-scheme:\s*light;\s*\}/);
    // the data-mode rules come after the @layer block closes
    const layerEnd = sem.lastIndexOf('@layer bbz');
    const modeRule = sem.indexOf("html[data-mode='dark']");
    expect(modeRule).toBeGreaterThan(layerEnd);
    expect(sem.slice(sem.indexOf("html[data-mode='light']"))).not.toContain('@layer');
  });

  it('keeps the DB font stack ahead of the system fallback', () => {
    expect(code('db-brand.css')).toMatch(/--db-font-family-sans:\s*'DB Screen Sans'/);
    expect(code('fonts.css')).toContain("font-family: 'DB Screen Sans';");
  });

  it('imports the theme parts in the documented order', () => {
    const imports = [...code('index.css').matchAll(/@import\s+'\.\/([\w-]+\.css)'/g)].map((m) => m[1]);
    expect(imports).toEqual([
      'db.css',
      'fonts.css',
      'semantic-tokens.css',
      'typography.css',
      'components.css',
      'mockup-surfaces.css',
    ]);
  });

  it('keeps the V10 mockup chrome on DB tokens — no raw hex colours', () => {
    const css = code('mockup-surfaces.css');
    // the mockup's ad-hoc navy palette must not leak in — every colour is a token
    const colourProps = [
      ...css.matchAll(/(?:^|[;{])\s*(background|color|border-color|fill|stroke)\s*:\s*([^;}]+)/g),
    ];
    const rawHex = colourProps
      .filter(([, , value]) => /#[0-9a-f]{3,8}\b/i.test(value))
      .map(([, prop, value]) => `${prop}: ${value.trim()}`);
    expect(rawHex).toEqual([]);
    expect(css).toMatch(/@layer bbz\s*\{/);
  });
});
