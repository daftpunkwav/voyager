/**
 * @file provider
 * @description Page-awareness probe for the activity page.
 *
 * Reports the feed entry count once loaded; returns null while loading or on
 * failure so no stale number is exposed.
 *
 * Responsibilities:
 * - Hold the module-level feed count cache written by ActivityPage
 * - Report a localized index line plus the events count, or null while
 *   the feed is not ready
 */

import { i18n } from '@/i18n';
import type { PageProbe } from '@/bridge/pageContext';

/** null = feed not ready (loading or failed); written by ActivityPage after data arrives. */
let feedCount: number | null = null;

export function rememberActivityFeedCount(count: number | null): void {
  feedCount = count;
}

export function lastActivityFeedCount(): number | null {
  return feedCount;
}

export const activityProvider: PageProbe = {
  page: 'activity',
  report() {
    // Return null when data is not ready so PageProbe skips this report (avoids empty reports)
    const n = feedCount;
    if (n === null) return null;
    return { summary: i18n.t('activity:probe.summary', { count: n }), counts: { events: n } };
  },
};
