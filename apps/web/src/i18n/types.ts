/**
 * @file i18n/types
 * @description Locale identifiers and resource-shape types for the i18n kernel.
 *
 * `LocaleId` is the closed set of supported UI locales (BCP 47). `system` is
 * not a locale: it is a user *choice* meaning "follow navigator.languages",
 * resolved to a concrete LocaleId by resolveLocale().
 */

/** Registered UI locales; extend together with resources/<locale>/ and the backend choices. */
export type LocaleId = 'zh-CN' | 'en';

/** A stored/user-facing locale selection: a concrete locale or "follow the system". */
export type LocaleChoice = LocaleId | 'system';

/** Resource bundle for one namespace: flat dotted keys, string values only. */
export type NamespaceResources = Record<string, string>;

/** All namespace bundles for one locale, keyed by namespace id (aligned with catalog.ts). */
export type LocaleResources = Record<string, NamespaceResources>;
