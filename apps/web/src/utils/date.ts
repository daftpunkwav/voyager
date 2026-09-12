/**
 * @file date
 * @description Locale-aware date/time formatting helpers (ISO 8601 in, localized text out).
 *
 * Thin ISO-string façade over i18n/format: the effective locale always
 * follows i18n.resolvedLanguage — never hardcode a locale here.
 *
 * Responsibilities:
 * - Format ISO 8601 timestamps as localized date/time and message times,
 *   with defined placeholders for null/invalid input
 * - Provide relative-time formatting for list rows
 *
 * This module must not depend on UI-layer components.
 */

import {
  formatDate as formatLocalizedDate,
  formatDateTime as formatLocalizedDateTime,
  formatRelativeTime as formatLocalizedRelativeTime,
  formatTime as formatLocalizedTime,
} from '@/i18n';

/** ISO 8601 -> localized date and time; null/undefined renders as "-". */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '-';
  return formatLocalizedDateTime(iso);
}

/** ISO 8601 -> localized date (e.g. 2026/05/12). */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return '-';
  return formatLocalizedDate(iso);
}

/** Message timestamp (HH:mm); invalid input renders as empty. */
export function formatMessageTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '';
  return formatLocalizedTime(d);
}

/** ISO 8601 -> relative time (e.g. "3 days ago"); invalid input passes through. */
export function formatRelativeTime(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return formatLocalizedRelativeTime(d);
}
