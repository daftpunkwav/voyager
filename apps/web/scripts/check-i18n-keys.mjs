/**
 * @file check-i18n-keys
 * @description Key-parity gate: for every namespace, all locales must expose
 * exactly the same top-level key set (flat dotted keys, string values).
 * Run via `npm run i18n:check`; exits non-zero with a diff report on drift.
 */

import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const resourcesDir = resolve(
  join(fileURLToPath(import.meta.url), '..', '..', 'src', 'i18n', 'resources')
);

const locales = readdirSync(resourcesDir).filter((name) =>
  statSync(join(resourcesDir, name)).isDirectory()
);
if (locales.length < 2) {
  console.error('[i18n:check] expected at least two locale directories');
  process.exit(1);
}

/** @returns {Map<string, string[]>} namespace -> sorted key list */
function collect(locale) {
  const dir = join(resourcesDir, locale);
  const map = new Map();
  for (const file of readdirSync(dir)) {
    if (!file.endsWith('.json')) continue;
    const ns = file.replace(/\.json$/, '');
    const raw = JSON.parse(readFileSync(join(dir, file), 'utf8'));
    const keys = Object.keys(raw);
    const bad = keys.filter((k) => typeof raw[k] !== 'string' || raw[k] === '');
    if (bad.length > 0) {
      console.error(
        `[i18n:check] ${locale}/${ns}: non-string or empty values for: ${bad.join(', ')}`
      );
      process.exitCode = 1;
    }
    map.set(ns, keys.sort());
  }
  return map;
}

const base = locales[0];
const baseMap = collect(base);
let failed = process.exitCode === 1;

for (const locale of locales.slice(1)) {
  const map = collect(locale);
  const nsMissing = [...baseMap.keys()].filter((ns) => !map.has(ns));
  const nsExtra = [...map.keys()].filter((ns) => !baseMap.has(ns));
  for (const ns of nsMissing) {
    console.error(`[i18n:check] ${locale} is missing namespace "${ns}"`);
    failed = true;
  }
  for (const ns of nsExtra) {
    console.error(`[i18n:check] ${locale} has extra namespace "${ns}"`);
    failed = true;
  }
  for (const [ns, baseKeys] of baseMap) {
    const keys = map.get(ns);
    if (!keys) continue;
    const missing = baseKeys.filter((k) => !keys.includes(k));
    const extra = keys.filter((k) => !baseKeys.includes(k));
    for (const k of missing) {
      console.error(`[i18n:check] ${locale}/${ns}.json missing key: ${k}`);
      failed = true;
    }
    for (const k of extra) {
      console.error(`[i18n:check] ${locale}/${ns}.json has extra key: ${k}`);
      failed = true;
    }
  }
}

if (failed) {
  console.error(`[i18n:check] FAILED (${locales.join(' vs ')})`);
  process.exit(1);
} else {
  console.log(
    `[i18n:check] OK: ${locales.join(', ')} in parity across ${baseMap.size} namespaces, ` +
      `${[...baseMap.values()].reduce((n, keys) => n + keys.length, 0)} keys per locale`
  );
}
