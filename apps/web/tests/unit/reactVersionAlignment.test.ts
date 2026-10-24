/**
 * @file reactVersionAlignment
 * @description Regression guard for the react / react-dom version pair.
 *
 * react-dom asserts at import time that the react package it loads carries
 * the exact same version and throws "Incompatible React versions" otherwise,
 * so a drifting pair aborts the app at startup. The pair enters the tree
 * from two manifests that move independently: the root overrides pin it,
 * while a dependency group bump rewrites the web app manifest only. npm then
 * resolves two react-dom copies and the mismatch reaches the runtime.
 *
 * Every point where the pair can drift is asserted below: the root override,
 * the web app manifest, the lockfile resolution and the installed tree the
 * app actually loads.
 */

import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const repoRoot = path.resolve(appRoot, '..', '..');

// Resolve from the app directory, the vantage point the vite aliases use: a
// copy nested under apps/web wins over the hoisted one.
const requireFromApp = createRequire(path.join(appRoot, 'package.json'));

/** An exact release version - a range would resolve the two packages apart. */
const EXACT_VERSION = /^\d+\.\d+\.\d+$/;

interface Manifest {
  dependencies?: Record<string, string>;
  overrides?: Record<string, string>;
}

interface Lockfile {
  packages?: Record<string, { version?: string }>;
}

function readJson<T>(file: string): T {
  return JSON.parse(readFileSync(file, 'utf8')) as T;
}

const rootManifest = readJson<Manifest>(path.join(repoRoot, 'package.json'));
const appManifest = readJson<Manifest>(path.join(appRoot, 'package.json'));
const lockfile = readJson<Lockfile>(path.join(repoRoot, 'package-lock.json'));

const rootOverrides = rootManifest.overrides ?? {};
const appDependencies = appManifest.dependencies ?? {};

/** Every copy of a package in the lockfile, hoisted or nested. */
function resolvedVersions(packageName: string): string[] {
  const entries = Object.entries(lockfile.packages ?? {}).filter(
    ([key]) => key === `node_modules/${packageName}` || key.endsWith(`/node_modules/${packageName}`)
  );
  return entries
    .map(([, entry]) => entry.version)
    .filter((version): version is string => typeof version === 'string');
}

function installedVersion(packageName: string): string {
  const manifestPath = requireFromApp.resolve(`${packageName}/package.json`);
  return readJson<{ version: string }>(manifestPath).version;
}

describe('react / react-dom version alignment', () => {
  it('pins react and react-dom to the same exact version in the root overrides', () => {
    expect(rootOverrides['react']).toMatch(EXACT_VERSION);
    expect(rootOverrides['react-dom']).toMatch(EXACT_VERSION);
    expect(rootOverrides['react-dom']).toBe(rootOverrides['react']);
  });

  it('declares react and react-dom at the same exact version in the web manifest', () => {
    expect(appDependencies['react']).toMatch(EXACT_VERSION);
    expect(appDependencies['react-dom']).toMatch(EXACT_VERSION);
    expect(appDependencies['react-dom']).toBe(appDependencies['react']);
  });

  it('keeps the root override in step with the web manifest', () => {
    expect(rootOverrides['react']).toBe(appDependencies['react']);
    expect(rootOverrides['react-dom']).toBe(appDependencies['react-dom']);
  });

  it('resolves every react and react-dom copy in the lockfile to one version', () => {
    const reactVersions = [...new Set(resolvedVersions('react'))];
    const reactDomVersions = [...new Set(resolvedVersions('react-dom'))];
    expect(reactVersions.length).toBeGreaterThan(0);
    expect(reactDomVersions.length).toBeGreaterThan(0);
    expect(reactVersions).toEqual(reactDomVersions);
    expect(reactVersions).toEqual([rootOverrides['react']]);
  });

  it('loads the pinned react and react-dom versions', () => {
    expect(installedVersion('react'), 'installed react is stale - run npm install').toBe(
      rootOverrides['react']
    );
    expect(installedVersion('react-dom'), 'installed react-dom is stale - run npm install').toBe(
      rootOverrides['react-dom']
    );
  });
});
