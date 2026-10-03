/**
 * Dependency policy check (npm side): fail on any banned package reaching the
 * tree - direct, transitive or override. Scans the workspace root
 * package-lock.json "packages" keys (the full resolved graph, workspace
 * members included) plus the root manifest declarations, so an entry in
 * dependency-policy.json blocks every path of arrival.
 */

import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const lockPath = join(repoRoot, "package-lock.json");
const manifestPath = join(repoRoot, "package.json");
const policyPath = join(repoRoot, "scripts", "ci", "dependency-policy.json");

const policy = JSON.parse(readFileSync(policyPath, "utf8"));
const banned = policy.npm ?? {};

const lock = JSON.parse(readFileSync(lockPath, "utf8"));
const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));

// Lock entries look like "web" or "web/node_modules/next"; the package name
// is everything after the last "node_modules/" segment. Alias installs
// ("local": "npm:real@...") hide the real package behind a local folder
// name - the spec string is the only place the real name shows.
const found = new Set();
const aliases = []; // { installed, target: "npm:<realname>@..." }
for (const [key, entry] of Object.entries(lock.packages ?? {})) {
  const installed = key.split("node_modules/").pop();
  if (installed) found.add(installed);
  // Aliased transitives may carry the real package name in entry.name while
  // only the node_modules key shows the alias - check both identities.
  if (typeof entry?.name === "string") found.add(entry.name);
  if (typeof entry?.version === "string" && entry.version.startsWith("npm:")) {
    aliases.push({ installed, target: entry.version });
  }
}
for (const section of ["dependencies", "devDependencies", "overrides"]) {
  for (const [installed, spec] of Object.entries(manifest[section] ?? {})) {
    found.add(installed);
    if (typeof spec === "string" && spec.startsWith("npm:")) {
      aliases.push({ installed, target: spec });
    }
  }
}

const violations = [...found]
  .filter((name) => banned[name] !== undefined)
  .sort();

const aliasViolations = aliases
  .map((alias) => ({ ...alias, real: alias.target.match(/^npm:(.+)@[^@]+$/)?.[1] ?? alias.target.slice(4) }))
  .filter((alias) => banned[alias.real] !== undefined)
  .sort((a, b) => a.installed.localeCompare(b.installed));

if (violations.length > 0 || aliasViolations.length > 0) {
  console.error("banned npm dependencies present:");
  for (const name of violations) {
    console.error(`  - ${name}: ${banned[name]}`);
  }
  for (const alias of aliasViolations) {
    console.error(
      `  - ${alias.installed} (alias for ${alias.real}): ${banned[alias.real]}`,
    );
  }
  process.exit(1);
}
console.log(`npm dependency policy ok (${found.size} packages scanned)`);
