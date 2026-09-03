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

  it('defines every --bbz-* colour token as a reference into the DB set', () => {
    const sem = code('semantic-tokens.css');
    const decls = [...sem.matchAll(/(--bbz-[\w-]+)\s*:\s*([^;]+);/g)];
    expect(decls.length).toBeGreaterThan(20);
    const rawHex = decls
      .filter(([, , value]) => /#[0-9a-f]{3,8}/i.test(value))
      .map(([, name]) => name);
    expect(rawHex).toEqual([]);
    // §13.9 priority meaning preserved, re-pointed at the DB semantic ramps
    expect(sem).toMatch(/--bbz-prio-low:\s*var\(--db-informational/);
    expect(sem).toMatch(/--bbz-prio-medium:\s*var\(--db-warning/);
    expect(sem).toMatch(/--bbz-prio-high:\s*var\(--db-critical/);
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
    ]);
  });
});
