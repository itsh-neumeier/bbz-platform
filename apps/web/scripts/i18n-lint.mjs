#!/usr/bin/env node
/**
 * i18n missing-key lint (E07-14 / #119).
 *
 * Scans `src/**` for `t('a.b.c')` / `$t("a.b")` / `i18n.global.t('…')` calls
 * with a *static* key and checks every one resolves in `src/i18n/de.json`.
 * Also flags keys defined in the locale that nothing references (dead keys),
 * as a warning. Exits non-zero on any missing key.
 */
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, extname, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const SRC = join(root, 'src');
const LOCALE = join(SRC, 'i18n', 'de.json');

const flatten = (obj, prefix = '') =>
  Object.entries(obj).flatMap(([k, v]) =>
    v && typeof v === 'object'
      ? flatten(v, prefix + k + '.')
      : [prefix + k],
  );

const locale = new Set(flatten(JSON.parse(readFileSync(LOCALE, 'utf8'))));

const walk = (dir) =>
  readdirSync(dir).flatMap((name) => {
    const p = join(dir, name);
    return statSync(p).isDirectory() ? walk(p) : p;
  });

// `t('a.b.c')` and `t('a.b.' + x)` (a dynamic suffix — treated as a namespace).
const KEY_RE = /(?:\$t|[^.\w]t|global\.t)\(\s*['"`]([\w.]+)['"`]/g;
const used = new Map(); // key -> first "file:line"

for (const file of walk(SRC)) {
  if (!['.ts', '.vue', '.mjs', '.js'].includes(extname(file))) continue;
  if (file === LOCALE) continue;
  const text = readFileSync(file, 'utf8');
  let m;
  while ((m = KEY_RE.exec(text))) {
    const key = m[1].replace(/\.$/, ''); // `a.b.` (dynamic) → the `a.b` namespace
    if (!used.has(key)) {
      const line = text.slice(0, m.index).split('\n').length;
      used.set(key, `${file.slice(root.length + 1)}:${line}`);
    }
  }
}

// A referenced *prefix* (e.g. `login.err.` + a dynamic suffix) is fine if any
// child exists; the scanner only catches the static part, so treat a key as
// present when it exists exactly or as a namespace with children.
const localeArr = [...locale];
const present = (key) =>
  locale.has(key) || localeArr.some((k) => k.startsWith(key + '.'));

const missing = [...used].filter(([k]) => !present(k));

// A key is "dead" only when its whole top-level namespace is unreferenced —
// individual keys are often reached dynamically (`t('ns.' + code)`, lookup maps)
// which a static scan cannot see. This still catches an abandoned section.
const usedNs = new Set([...used.keys()].map((k) => k.split('.')[0]));
const dead = localeArr.filter((k) => !usedNs.has(k.split('.')[0]));

if (dead.length) {
  console.warn(`i18n: ${dead.length} key(s) in an unreferenced namespace:`);
  for (const k of dead) console.warn(`  - ${k}`);
}

if (missing.length) {
  console.error(`\ni18n: ${missing.length} missing key(s) in de.json:`);
  for (const [k, where] of missing) console.error(`  - ${k}   (${where})`);
  process.exit(1);
}

console.log(`i18n ok — ${used.size} keys referenced, all resolve in de.json`);
