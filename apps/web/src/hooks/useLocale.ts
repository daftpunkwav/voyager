/**
 * @file useLocale
 * @description UI-language selection. The backend (appearance.locale) is the
 * single source of truth, symmetric to useTheme: changes persist via
 * set_setting first, then sync locally (store + html[lang] + i18n) through
 * shell/localeBridge without waiting for settings.changed. Failures propagate
 * to the caller so the UI can toast without switching.
 */

import { callCapability } from '@/bridge/client';
import { syncLocale } from '@/shell/localeBridge';
import { useUIStore } from '@/stores/uiStore';
import type { LocaleChoice } from '@/i18n/types';

export function useLocale() {
  const locale = useUIStore((s) => s.locale);

  /** Change UI language: persist to the backend first, then sync locally; failures propagate. */
  const changeLocale = async (next: LocaleChoice) => {
    await callCapability('settings', 'set_setting', {
      key: 'appearance.locale',
      value: next,
    });
    syncLocale(next);
  };

  return { locale, changeLocale };
}
