/**
 * @file localeBridge.ts
 * @description Locale bridge with the backend appearance.locale as the single
 * source of truth, symmetric to themeBridge:
 *
 * This file is the only place that applies document.documentElement.lang and
 * calls i18n.changeLanguage (stores/components never touch either):
 * - startup: get_setting -> syncLocale (backend unreachable keeps the local
 *   selection / default; shell rendering is never blocked);
 * - settings.changed (from user or agent) -> syncLocale, idempotent.
 * User changes persist via set_setting first (hooks/useLocale), then take
 * effect uniformly through this bridge.
 *
 * Responsibilities:
 * - Apply html[lang] and i18n.changeLanguage as the single application point
 * - Sync the locale at startup and on settings.changed, idempotently
 */

import { useEffect } from 'react';
import { callCapability } from '@/bridge/client';
import { subscribe } from '@/bridge/stream';
import { useUIStore } from '@/stores/uiStore';
import { i18n } from '@/i18n';
import { normalizeLocaleChoice, resolveLocale } from '@/i18n/config';
import type { LocaleChoice } from '@/i18n/types';

interface LocalePayload {
  key?: string;
  value?: unknown;
}

/** The only DOM/i18n application: html[lang] + changeLanguage to the resolved locale. */
export function applyLocale(choice: LocaleChoice): void {
  const effective = resolveLocale(choice);
  document.documentElement.lang = effective;
  if (i18n.language !== effective) {
    void i18n.changeLanguage(effective);
  }
}

/** Backend source of truth -> store selection + DOM/i18n, in one idempotent step
 *  (shared by startup, hot updates and the post-save local sync). */
export function syncLocale(requested: unknown): void {
  const choice = normalizeLocaleChoice(requested);
  useUIStore.getState().setLocale(choice);
  applyLocale(choice);
}

export function useLocaleBridge() {
  useEffect(() => {
    let alive = true;
    callCapability<{ key: string; value?: unknown }>('settings', 'get_setting', {
      key: 'appearance.locale',
    })
      .then((item) => {
        if (alive && item) syncLocale(item.value);
      })
      .catch(() => {
        // Settings unreadable (e.g. backend not running): keep the persisted
        // selection / default, don't break shell rendering
      });

    const off = subscribe(['settings.changed'], (event) => {
      const payload = event.payload as LocalePayload;
      if (payload.key === 'appearance.locale') {
        syncLocale(payload.value);
      }
    });

    return () => {
      alive = false;
      off();
    };
  }, []);
}
