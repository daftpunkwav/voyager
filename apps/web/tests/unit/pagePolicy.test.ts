/**
 * @file pagePolicy
 * @description Unit coverage for the policy the shipped page carries.
 *
 * The page states its Content Security Policy in a meta tag, and the build
 * keeps it: the dev server relaxes script-src for the React Fast Refresh
 * preamble it injects, the built output does not. A regression in either would
 * ship a page that allows inline script or eval again, so both are asserted
 * here rather than left to the browser report.
 */

import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import type { Plugin, UserConfig } from 'vite';

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const INDEX_HTML = readFileSync(path.join(appRoot, 'index.html'), 'utf8');

/** The policy the page states, as its directives. */
function pagePolicy(html: string): Map<string, string> {
  const marker = 'http-equiv="Content-Security-Policy"';
  const at = html.indexOf(marker);
  expect(at, 'the page states no Content Security Policy').toBeGreaterThan(-1);
  const start = html.indexOf('content="', at) + 'content="'.length;
  const end = html.indexOf('"', start);
  const directives = new Map<string, string>();
  for (const part of html.slice(start, end).split(';')) {
    const [name, ...sources] = part.trim().split(/\s+/);
    if (name) directives.set(name, sources.join(' '));
  }
  return directives;
}

/** The plugin that fills the brand placeholders into the page. */
function brandPlugin(config: UserConfig): Plugin {
  const plugin = (config.plugins ?? []).find(
    (entry): entry is Plugin =>
      entry !== null && typeof entry === 'object' && entry.name === 'inject-brand'
  );
  expect(plugin, 'the build no longer fills the brand into the page').toBeDefined();
  return plugin as Plugin;
}

/** The page as the build writes it, without a dev server behind it. */
async function builtPage(config: UserConfig): Promise<string> {
  const hook = brandPlugin(config).transformIndexHtml;
  const transform = typeof hook === 'function' ? hook : hook?.handler;
  expect(typeof transform, 'the brand plugin no longer transforms the page').toBe('function');
  return (transform as (html: string, ctx: unknown) => Promise<string>)(INDEX_HTML, {});
}

describe('page policy', () => {
  it('allows no inline script and no eval in the page', () => {
    const directives = pagePolicy(INDEX_HTML);
    expect(directives.get('default-src')).toBe("'self'");
    expect(directives.get('script-src')).toBe("'self'");
    expect(directives.get('worker-src')).toBe("'self'");
    expect(directives.get('object-src')).toBe("'none'");
  });

  it('keeps the strict policy in the built page', async () => {
    const config = (await import('../../vite.config')).default as UserConfig;
    const directives = pagePolicy(await builtPage(config));
    expect(directives.get('script-src')).toBe("'self'");
    expect(directives.get('worker-src')).toBe("'self'");
    expect(directives.get('object-src')).toBe("'none'");
  });

  it('loads the first-paint sync as a script of its own', () => {
    // The policy forbids inline script, so the theme sync has to be a file.
    expect(INDEX_HTML).toContain('src="/theme-init.js"');
    expect(INDEX_HTML).toContain('data-ui-store-key=');
  });
});
