/**
 * @file i18n/format
 * @description Intl-based formatting that follows the active i18n language,
 * for React and non-React callers alike (reads the i18n instance, never a
 * React context). Business code must not hardcode 'zh-CN' — go through here.
 *
 * Responsibilities:
 * - Format dates, times, numbers, and relative time via Intl following
 *   i18n.resolvedLanguage, passing unparseable input through
 * - Keep a 24-hour clock regardless of locale and cache relative-time
 *   formatters per language
 *
 * This module must not depend on UI-layer components.
 */

import { i18n } from './bootstrap';
import { DEFAULT_LOCALE } from './config';

type DateInput = Date | number | string;

/** Current effective locale for formatting (i18n.resolvedLanguage, guarded before init). */
function currentLocale(): string {
  return i18n.resolvedLanguage ?? i18n.language ?? DEFAULT_LOCALE;
}

function toDate(value: DateInput): Date | null {
  const d = value instanceof Date ? value : new Date(value);
  return Number.isNaN(d.getTime()) ? null : d;
}

const DATE_OPTS: Intl.DateTimeFormatOptions = { year: 'numeric', month: '2-digit', day: '2-digit' };
// Product decision: always a 24-hour clock regardless of locale (hour12 would
// flip to AM/PM under en).
const TIME_OPTS: Intl.DateTimeFormatOptions = { hour: '2-digit', minute: '2-digit', hour12: false };
const DATETIME_OPTS: Intl.DateTimeFormatOptions = { ...DATE_OPTS, ...TIME_OPTS };

/** Localized date (2026/05/12 style). Returns the raw input string when unparseable. */
export function formatDate(value: DateInput, opts?: Intl.DateTimeFormatOptions): string {
  const d = toDate(value);
  if (!d) return value instanceof Date ? '' : String(value);
  return new Intl.DateTimeFormat(currentLocale(), { ...DATE_OPTS, ...opts }).format(d);
}

/** Localized date + time. Returns the raw input string when unparseable. */
export function formatDateTime(value: DateInput, opts?: Intl.DateTimeFormatOptions): string {
  const d = toDate(value);
  if (!d) return value instanceof Date ? '' : String(value);
  return new Intl.DateTimeFormat(currentLocale(), { ...DATETIME_OPTS, ...opts }).format(d);
}

/** Localized clock time (HH:mm). */
export function formatTime(value: DateInput, opts?: Intl.DateTimeFormatOptions): string {
  const d = toDate(value);
  if (!d) return value instanceof Date ? '' : String(value);
  return new Intl.DateTimeFormat(currentLocale(), { ...TIME_OPTS, ...opts }).format(d);
}

/** Locale-aware number grouping (12,345). */
export function formatNumber(value: number, opts?: Intl.NumberFormatOptions): string {
  return new Intl.NumberFormat(currentLocale(), opts).format(value);
}

const relativeFormatters = new Map<string, Intl.RelativeTimeFormat>();

/** Shared RelativeTimeFormat per locale (recreated only when the language switches). */
function relativeFormatter(): Intl.RelativeTimeFormat {
  const locale = currentLocale();
  let rtf = relativeFormatters.get(locale);
  if (!rtf) {
    rtf = new Intl.RelativeTimeFormat(locale, { numeric: 'auto' });
    relativeFormatters.set(locale, rtf);
  }
  return rtf;
}

/** Relative time from now ("3 天前" / "3 days ago"). */
export function formatRelativeTime(value: DateInput): string {
  const d = toDate(value);
  if (!d) return value instanceof Date ? '' : String(value);

  const diffMs = d.getTime() - Date.now();
  const diffSec = Math.round(diffMs / 1000);
  const absSec = Math.abs(diffSec);
  const rtf = relativeFormatter();

  if (absSec < 60) return rtf.format(diffSec, 'second');
  const diffMin = Math.round(diffSec / 60);
  if (Math.abs(diffMin) < 60) return rtf.format(diffMin, 'minute');
  const diffHour = Math.round(diffMin / 60);
  if (Math.abs(diffHour) < 24) return rtf.format(diffHour, 'hour');
  const diffDay = Math.round(diffHour / 24);
  if (Math.abs(diffDay) < 30) return rtf.format(diffDay, 'day');
  const diffMonth = Math.round(diffDay / 30);
  if (Math.abs(diffMonth) < 12) return rtf.format(diffMonth, 'month');
  const diffYear = Math.round(diffMonth / 12);
  return rtf.format(diffYear, 'year');
}
