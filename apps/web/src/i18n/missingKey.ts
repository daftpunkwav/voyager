/**
 * @file i18n/missingKey
 * @description Development-time missing-key reporting. Production behavior
 * needs no handler: i18next falls back to fallbackLng (zh-CN) and finally to
 * the key itself, so the UI never renders blank for a missing translation.
 */

import type { i18n as I18n } from 'i18next';

/** Attach the dev-only missingKey logger to an i18n instance (idempotent per instance). */
export function registerMissingKeyHandler(instance: I18n): void {
  instance.on('missingKey', (lngs: readonly string[], ns: string, key: string) => {
    if (import.meta.env.DEV) {
      console.warn(`[i18n] missing key "${ns}:${key}" for [${lngs.join(', ')}]`);
    }
  });
}
