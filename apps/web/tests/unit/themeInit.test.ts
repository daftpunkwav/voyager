/**
 * @file themeInit
 * @description Unit coverage for the first-paint theme and locale sync
 * (public/theme-init.js).
 *
 * The initializer runs in <head> before the app renders, so a regression in it
 * reaches every page as a flash of the wrong theme or the wrong language. The
 * tests run the shipped file itself, the way the page loads it.
 */

import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const appRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const THEME_INIT_SOURCE = readFileSync(path.join(appRoot, 'public', 'theme-init.js'), 'utf8');

/** Store keys the build puts on the script tag. */
const UI_STORE_KEY = 'voyager-ui-store';
const UI_STORE_LEGACY_KEY = 'voyager-ui-store-legacy';

/** The script tag the build renders, with the store keys it carries. */
function scriptTag(): HTMLScriptElement {
  const script = document.createElement('script');
  script.setAttribute('data-ui-store-key', UI_STORE_KEY);
  script.setAttribute('data-ui-store-legacy-key', UI_STORE_LEGACY_KEY);
  return script;
}

/** Run the initializer the way the page does, before the first paint. */
function runThemeInit(): void {
  new Function(THEME_INIT_SOURCE)();
}

/** The theme and locale the initializer left on the document element. */
function appliedState(): { theme: string | null; locale: string | null } {
  return {
    theme: document.documentElement.getAttribute('data-theme'),
    locale: document.documentElement.getAttribute('lang'),
  };
}

/** Store a UI state the way the app persists it. */
function storeState(key: string, state: { theme?: string; locale?: string }): void {
  localStorage.setItem(key, JSON.stringify({ state }));
}

describe('theme initialization', () => {
  beforeEach(() => {
    localStorage.clear();
    document.documentElement.setAttribute('data-theme', 'light');
    document.documentElement.setAttribute('lang', 'zh-CN');
    // The initializer reads its store keys from the script tag it runs in.
    Object.defineProperty(document, 'currentScript', {
      configurable: true,
      get: () => scriptTag(),
    });
    vi.stubGlobal('matchMedia', (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }));
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
    Reflect.deleteProperty(document, 'currentScript');
    Reflect.deleteProperty(navigator, 'languages');
  });

  it('applies the stored theme and locale', () => {
    storeState(UI_STORE_KEY, { theme: 'dark', locale: 'en' });
    runThemeInit();
    expect(appliedState()).toEqual({ theme: 'dark', locale: 'en' });
  });

  it('applies the stored light theme and Chinese locale', () => {
    storeState(UI_STORE_KEY, { theme: 'light', locale: 'zh-CN' });
    runThemeInit();
    expect(appliedState()).toEqual({ theme: 'light', locale: 'zh-CN' });
  });

  it('falls back to the system preference and the default locale', () => {
    runThemeInit();
    expect(appliedState()).toEqual({ theme: 'light', locale: 'zh-CN' });
  });

  it('follows the system preference when the theme is not decided yet', () => {
    vi.stubGlobal('matchMedia', (query: string) => ({
      matches: true,
      media: query,
      onchange: null,
      addEventListener: () => {},
      removeEventListener: () => {},
      addListener: () => {},
      removeListener: () => {},
      dispatchEvent: () => false,
    }));
    // The system locale is the first browser language the app knows.
    Object.defineProperty(navigator, 'languages', {
      configurable: true,
      get: () => ['zh-CN', 'en'],
    });
    storeState(UI_STORE_KEY, { theme: 'system', locale: 'system' });
    runThemeInit();
    expect(appliedState()).toEqual({ theme: 'dark', locale: 'zh-CN' });
  });

  it('reads the legacy store key when the current one holds nothing', () => {
    storeState(UI_STORE_LEGACY_KEY, { theme: 'dark', locale: 'en' });
    runThemeInit();
    expect(appliedState()).toEqual({ theme: 'dark', locale: 'en' });
  });

  it('keeps the defaults when the storage is unavailable', () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('The storage is not available.');
    });
    runThemeInit();
    expect(appliedState()).toEqual({ theme: 'light', locale: 'zh-CN' });
  });
});
