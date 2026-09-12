/**
 * @file instanceFormat
 * @description Display formatting helpers for team-page instance and checkpoint entries.
 *
 * Responsibilities:
 * - Format Unix-second start times as relative "time ago" copy
 * - Map instance statuses to status chip classes
 */

import { i18n } from '@/i18n';

/** started_ts is a Unix timestamp in seconds (time.time() in agent/runtime/state.py). */
export function relativeTime(ts: number): string {
  if (!ts) return '';
  const diff = Math.max(0, Date.now() / 1000 - ts);
  if (diff < 60) return i18n.t('team:time.justNow');
  if (diff < 3600) return i18n.t('team:time.minutesAgo', { n: Math.floor(diff / 60) });
  if (diff < 86400) return i18n.t('team:time.hoursAgo', { n: Math.floor(diff / 3600) });
  return i18n.t('team:time.daysAgo', { n: Math.floor(diff / 86400) });
}

/** Instance status → status chip class (shell.css .inst--*). */
export function statusChipClass(status: string): string {
  switch (status) {
    case 'running':
      return 'inst--running';
    case 'completed':
      return 'inst--done';
    case 'failed':
      return 'inst--failed';
    case 'paused':
      return 'inst--paused';
    default:
      return 'inst--muted';
  }
}
