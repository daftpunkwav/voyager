/**
 * @file i18n/index
 * @description The deliberately narrow public surface of the i18n kernel.
 * Components should use useTranslation() (react-i18next) + useLocale();
 * import from here only for the instance, constants, and formatters.
 */

export { initI18n, i18n } from './bootstrap';
export { SUPPORTED_LOCALES, DEFAULT_LOCALE, isLocaleId } from './config';
export { formatDate, formatDateTime, formatTime, formatNumber, formatRelativeTime } from './format';
export type { LocaleId } from './types';
