/**
 * @file i18n/config
 * @description Locale model constants and pure resolution logic (no side effects).
 *
 * Extending to a new language requires exactly: add the member to LocaleId,
 * add resources/<locale>/ bundles, add the value to the backend
 * `appearance.locale` choices, and list it here.
 *
 * Responsibilities:
 * - Define the supported locale set, the factory default, and the
 *   locale-choice type
 * - Normalize raw stored values against the closed set
 * - Resolve 'system' against navigator.languages with primary-subtag
 *   best-match and a default fallback
 *
 * This module must not depend on UI-layer components.
 */

import type { LocaleChoice, LocaleId } from './types';

export type { LocaleChoice, LocaleId } from './types';

/** Factory default; the product is Chinese-first. */
export const DEFAULT_LOCALE: LocaleId = 'zh-CN';

/** All supported locales; index [0] doubles as the fallback language. */
export const SUPPORTED_LOCALES: readonly LocaleId[] = ['zh-CN', 'en'] as const;

/** Runtime check against the closed LocaleId set (guards against dirty stored values). */
export function isLocaleId(value: unknown): value is LocaleId {
  return typeof value === 'string' && (SUPPORTED_LOCALES as readonly string[]).includes(value);
}

function isLocaleChoice(value: unknown): value is LocaleChoice {
  return value === 'system' || isLocaleId(value);
}

/** Normalize a raw stored value to a valid choice; anything else falls back to the default locale. */
export function normalizeLocaleChoice(value: unknown): LocaleChoice {
  return isLocaleChoice(value) ? value : DEFAULT_LOCALE;
}

/** Best-match a single language tag against the supported list (exact, then primary subtag). */
function matchLocale(tag: string): LocaleId | undefined {
  const lower = tag.toLowerCase();
  const exact = SUPPORTED_LOCALES.find((l) => l.toLowerCase() === lower);
  if (exact) return exact;
  const primary = lower.split('-')[0];
  return SUPPORTED_LOCALES.find((l) => l.toLowerCase().split('-')[0] === primary);
}

/** Resolve a user choice to the effective locale. 'system' follows navigator.languages,
 *  falling back to DEFAULT_LOCALE when nothing matches (or navigator is unavailable). */
export function resolveLocale(requested: LocaleChoice | unknown): LocaleId {
  const choice = normalizeLocaleChoice(requested);
  if (choice !== 'system') return choice;
  if (typeof navigator === 'undefined') return DEFAULT_LOCALE;
  const candidates = navigator.languages?.length ? navigator.languages : [navigator.language];
  for (const tag of candidates) {
    const hit = tag ? matchLocale(tag) : undefined;
    if (hit) return hit;
  }
  return DEFAULT_LOCALE;
}
