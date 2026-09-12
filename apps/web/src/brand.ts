/**
 * @file brand
 * @description Frontend brand layer. Values are injected by Vite from the
 * repo-root brand.json (single source of truth).
 */

export const PRODUCT_NAME: string = __BRAND__.productName;
export const STORAGE = __BRAND__.storage;

/** Migrate a legacy key to the neutral key; an existing new value discards the old one. */
export function migrateKey(current: string, legacy: string): void {
  try {
    if (typeof localStorage === 'undefined') return;
    if (localStorage.getItem(current) != null) {
      localStorage.removeItem(legacy);
      return;
    }
    const old = localStorage.getItem(legacy);
    if (old != null) {
      localStorage.setItem(current, old);
      localStorage.removeItem(legacy);
    }
  } catch {
    /* private browsing mode */
  }
}

export function readKey(current: string, legacy: string): string | null {
  try {
    return localStorage.getItem(current) ?? localStorage.getItem(legacy);
  } catch {
    return null;
  }
}

export function writeKey(current: string, value: string): void {
  try {
    localStorage.setItem(current, value);
  } catch {
    /* noop */
  }
}
