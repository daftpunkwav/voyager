/**
 * @file i18n/bootstrap
 * @description The single i18next initialization. Bundles are inlined (static
 * imports, no async backend), so init completes synchronously and t() is
 * usable in the same tick — no first-paint gap.
 *
 * Idempotent: repeated initI18n() calls return the already-initialized
 * singleton. The initial language comes from the persisted uiStore selection
 * (same shape the index.html inline script reads), so a chosen locale survives
 * a reload without a flash; the runtime source of truth stays the backend
 * `appearance.locale` via shell/localeBridge.
 *
 * Responsibilities:
 * - Initialize i18next synchronously with inlined per-locale bundle
 *   imports (no async backend)
 * - Seed the initial language from the persisted uiStore choice, falling
 *   back to the default locale
 * - Configure flat dotted keys with ':' namespace selection and the
 *   fallback chain; attach the dev missing-key handler
 * - Stay idempotent: repeated initI18n() calls return the singleton
 *
 * This module must not depend on UI-layer components.
 */

import i18next, { type i18n as I18n } from 'i18next';
import { initReactI18next } from 'react-i18next';
import { STORAGE } from '@/brand';
import { DEFAULT_LOCALE, SUPPORTED_LOCALES, isLocaleId, resolveLocale } from './config';
import { DEFAULT_NS, NAMESPACES } from './catalog';
import { registerMissingKeyHandler } from './missingKey';
import type { LocaleChoice } from './types';

import enCommon from './resources/en/common.json';
import enErrors from './resources/en/errors.json';
import enOverview from './resources/en/overview.json';
import enShell from './resources/en/shell.json';
import enSettings from './resources/en/settings.json';
import enNotes from './resources/en/notes.json';
import enSources from './resources/en/sources.json';
import enTeam from './resources/en/team.json';
import enGraph from './resources/en/graph.json';
import enCodeGraph from './resources/en/codeGraph.json';
import enActivity from './resources/en/activity.json';
import enUsage from './resources/en/usage.json';
import enHealth from './resources/en/health.json';
import enChat from './resources/en/chat.json';
import enAgent from './resources/en/agent.json';
import zhCommon from './resources/zh-CN/common.json';
import zhErrors from './resources/zh-CN/errors.json';
import zhOverview from './resources/zh-CN/overview.json';
import zhShell from './resources/zh-CN/shell.json';
import zhSettings from './resources/zh-CN/settings.json';
import zhNotes from './resources/zh-CN/notes.json';
import zhSources from './resources/zh-CN/sources.json';
import zhTeam from './resources/zh-CN/team.json';
import zhGraph from './resources/zh-CN/graph.json';
import zhCodeGraph from './resources/zh-CN/codeGraph.json';
import zhActivity from './resources/zh-CN/activity.json';
import zhUsage from './resources/zh-CN/usage.json';
import zhHealth from './resources/zh-CN/health.json';
import zhChat from './resources/zh-CN/chat.json';
import zhAgent from './resources/zh-CN/agent.json';

const resources = {
  'zh-CN': {
    common: zhCommon,
    errors: zhErrors,
    overview: zhOverview,
    shell: zhShell,
    settings: zhSettings,
    notes: zhNotes,
    sources: zhSources,
    team: zhTeam,
    graph: zhGraph,
    codeGraph: zhCodeGraph,
    activity: zhActivity,
    usage: zhUsage,
    health: zhHealth,
    chat: zhChat,
    agent: zhAgent,
  },
  en: {
    common: enCommon,
    errors: enErrors,
    overview: enOverview,
    shell: enShell,
    settings: enSettings,
    notes: enNotes,
    sources: enSources,
    team: enTeam,
    graph: enGraph,
    codeGraph: enCodeGraph,
    activity: enActivity,
    usage: enUsage,
    health: enHealth,
    chat: enChat,
    agent: enAgent,
  },
} as const;

/** Read the persisted locale choice from the uiStore persist payload (best effort). */
function readStoredLocaleChoice(): LocaleChoice | undefined {
  try {
    const raw = window.localStorage.getItem(STORAGE.uiStore);
    if (!raw) return undefined;
    const parsed = JSON.parse(raw) as { state?: { locale?: unknown } };
    const value = parsed.state?.locale;
    return value === 'system' || isLocaleId(value) ? value : undefined;
  } catch {
    return undefined;
  }
}

export interface InitI18nOptions {
  /** Explicit initial choice; defaults to the persisted selection, then the default locale. */
  lng?: LocaleChoice;
}

/** Initialize (once) and return the global i18n instance. */
export function initI18n(options: InitI18nOptions = {}): I18n {
  if (i18next.isInitialized) return i18next;
  const choice = options.lng ?? readStoredLocaleChoice() ?? DEFAULT_LOCALE;
  void i18next.use(initReactI18next).init({
    lng: resolveLocale(choice),
    fallbackLng: DEFAULT_LOCALE,
    supportedLngs: SUPPORTED_LOCALES as unknown as string[],
    ns: NAMESPACES as unknown as string[],
    defaultNS: DEFAULT_NS,
    resources,
    // Flat dotted keys ("appearance.locale.label") are matched literally;
    // namespaces are selected with the ':' prefix (t('shell:nav.chat')).
    keySeparator: false,
    nsSeparator: ':',
    interpolation: { escapeValue: false },
    returnEmptyString: false,
    react: { useSuspense: false },
  });
  registerMissingKeyHandler(i18next);
  return i18next;
}

/** The global i18n instance (for bridges and non-React callers). Call initI18n() first. */
export const i18n = i18next;
