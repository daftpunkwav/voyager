/**
 * @file pageContext.ts
 * @description Page-awareness protocol: one probe per page whose report() emits an
 * index row plus summary.
 *
 * Summaries never expose body content; probes return null while their data
 * is still loading and PageProbe skips that report. This file defines the
 * protocol only — each page implements it in its own provider.ts (page
 * autonomy).
 */

export interface PageProbe {
  /** Page identifier (sent to the backend as the page field) */
  page: string;
  /** Report the current page summary (a single controllable-length index line) + counts + current selection (may be empty) */
  report(): { summary: string; counts?: Record<string, number>; selected?: string } | null;
}
