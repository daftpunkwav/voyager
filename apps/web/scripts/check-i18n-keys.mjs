/**
 * @file check-i18n-keys
 * @description Key-parity gate plus code-usage cross-check. For every
 * namespace, all locales must expose exactly the same top-level key set
 * (flat dotted keys, string values). Additionally, translation keys
 * referenced from source must exist in the dictionaries: literal
 * `t('ns:key')` / `t('key')` (resolved against the namespace bound by
 * `useTranslation('ns')` in the same file) and `i18n.t('ns:key')` are
 * hard errors when missing; dynamic templates like `t(\`toolPerms.mode.${m}\`)`
 * mark their whole `prefix.*` subtree as referenced. Dictionary keys that
 * no reference reaches are reported as dead but do not fail the gate —
 * schema-driven dynamic lookups (`t(\`auto.${key}\`, { defaultValue })`)
 * cannot be resolved statically. Run via `npm run i18n:check`; exits
 * non-zero with a diff report on drift.
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

// ---- Code-usage cross-check: source references vs dictionaries ----

const srcDir = resolve(join(fileURLToPath(import.meta.url), '..', '..', 'src'));

/** @returns {string[]} absolute paths of .ts/.tsx files under dir, recursively */
function walkSource(dir) {
  const out = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) out.push(...walkSource(full));
    else if (/\.(ts|tsx)$/.test(entry)) out.push(full);
  }
  return out;
}

/** Blank out line and block comments while preserving string literals, so
 * prose examples like `t('shell:nav.chat')` in a comment are not scanned
 * as code references. */
function stripComments(src) {
  let out = '';
  let i = 0;
  let mode = 'code'; // code | line | block
  let quote = null;
  while (i < src.length) {
    const c = src[i];
    const next = src[i + 1];
    if (quote) {
      out += c;
      if (c === '\\') {
        out += next ?? '';
        i += 2;
        continue;
      }
      if (c === quote) quote = null;
      i += 1;
      continue;
    }
    if (mode === 'line') {
      if (c === '\n') {
        mode = 'code';
        out += c;
      }
      i += 1;
      continue;
    }
    if (mode === 'block') {
      if (c === '*' && next === '/') {
        mode = 'code';
        i += 2;
        out += ' ';
      } else i += 1;
      continue;
    }
    if (c === '"' || c === "'" || c === '`') {
      quote = c;
      out += c;
      i += 1;
      continue;
    }
    if (c === '/' && next === '/') {
      mode = 'line';
      i += 2;
      continue;
    }
    if (c === '/' && next === '*') {
      mode = 'block';
      i += 2;
      continue;
    }
    out += c;
    i += 1;
  }
  return out;
}

function collectUsage() {
  const referenced = new Set(); // "ns:key" literals proven used
  const prefixes = new Set(); // "ns:prefix." subtrees proven used via templates
  for (const file of walkSource(srcDir)) {
    const code = stripComments(readFileSync(file, 'utf8'));
    // Lexical binding: a prefix-less key belongs to the nearest
    // useTranslation('ns') call preceding it in source order. Files can
    // host several components with different namespaces (Sidebar binds
    // both 'chat' and 'shell'), so a file-wide cross-product would
    // invent references that exist in neither dictionary.
    const bindings = [...code.matchAll(/useTranslation\(\s*['"]([a-zA-Z0-9_-]+)['"]/g)].map(
      (m) => ({ at: m.index, ns: m[1] })
    );
    const nsAt = (pos) => {
      let ns = null;
      for (const b of bindings) {
        if (b.at >= pos) break;
        ns = b.ns;
      }
      return ns;
    };
    // Literal keys: t('ns:key'), t('key'), i18n.t('ns:key'). \bt\( only
    // matches a callee named exactly t (identifier-final t keeps a word
    // char to its left, so parseInt/select/assert never match).
    for (const m of code.matchAll(/\bt\(\s*(['"])(?:([a-zA-Z0-9_-]+):)?([a-zA-Z0-9_.-]+)\1/g)) {
      const ns = m[2] ?? nsAt(m.index);
      if (ns) referenced.add(`${ns}:${m[3]}`);
    }
    // Dynamic templates: t(`ns:prefix.${x}`) / t(`prefix.${x}`)
    for (const m of code.matchAll(/\bt\(\s*`(?:([a-zA-Z0-9_-]+):)?([a-zA-Z0-9_.-]+)\$\{/g)) {
      const ns = m[1] ?? nsAt(m.index);
      if (ns) prefixes.add(`${ns}:${m[2]}.`);
    }
  }
  return { referenced, prefixes };
}

const { referenced, prefixes } = collectUsage();
const dictionaryKeys = new Set();
for (const [ns, keys] of baseMap) for (const k of keys) dictionaryKeys.add(`${ns}:${k}`);

const isAlive = (k) => referenced.has(k) || [...prefixes].some((p) => k.startsWith(p));

const usedMissing = [...referenced].filter((k) => !dictionaryKeys.has(k)).sort();
const deadKeys = [...dictionaryKeys].filter((k) => !isAlive(k)).sort();

for (const k of usedMissing) {
  console.error(`[i18n:check] referenced in code but missing from dictionaries: ${k}`);
  failed = true;
}
if (deadKeys.length > 0) {
  const shown = deadKeys.slice(0, 15).join(', ');
  console.warn(
    `[i18n:check] NOTE ${deadKeys.length} dead dictionary keys (no code reference, informational only): ${shown}` +
      (deadKeys.length > 15 ? ', …' : '')
  );
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
