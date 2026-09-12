/**
 * @file PageProbe
 * @description Page-awareness component mounted in AppShell: route changes emit
 * page_view plus a page summary report; the summary refreshes every 30s and
 * selection changes are reported as they happen. Fully silent when the privacy
 * switch is off.
 *
 * Responsibilities:
 * - Emit page_view and a delayed page summary on every route change
 * - Refresh summaries every 30s and poll selection changes every 2s
 * - Follow the privacy switch hot toggle and stay fully silent when off
 */

import { useEffect, useRef, useCallback } from 'react';
import { useLocation } from 'react-router-dom';
import { reportPageContext } from '@/api/agent';
import {
  initActivityReport,
  activityReportEnabled,
  reportPageView,
  setActivityReportEnabled,
} from '@/bridge/activity';
import { subscribe } from '@/bridge/stream';
import { resolvePageProbe } from '@/shell/pageProbes';

const SUMMARY_INTERVAL_MS = 30_000;
const SELECTION_POLL_MS = 2000;
const INITIAL_DELAY_MS = 800;

export function PageProbe() {
  const location = useLocation();
  const lastSelected = useRef('');
  const timersRef = useRef<{ t1: number | null; summary: number | null; selection: number | null }>(
    {
      t1: null,
      summary: null,
      selection: null,
    }
  );

  useEffect(() => {
    void initActivityReport();
    // Hot toggle: turning the switch off takes effect immediately (no further reports);
    // the module is statically bundled, so call it directly
    return subscribe(['settings.changed'], (ev) => {
      if (ev.payload.key === 'privacy.activity_report') {
        setActivityReportEnabled(ev.payload.value !== false);
      }
    });
  }, []);

  // Clear every timer belonging to the current route
  const clearTimers = useCallback(() => {
    const { t1, summary, selection } = timersRef.current;
    if (t1 != null) window.clearTimeout(t1);
    if (summary != null) window.clearInterval(summary);
    if (selection != null) window.clearInterval(selection);
    timersRef.current = { t1: null, summary: null, selection: null };
  }, []);

  const reportSummary = useCallback(() => {
    if (!activityReportEnabled()) return;
    const probe = resolvePageProbe(location.pathname);
    if (!probe) return;
    const out = probe.report();
    if (!out) return; // Data not ready yet; never report an empty page
    lastSelected.current = out.selected ?? '';
    void reportPageContext({
      page: probe.page,
      summary: out.summary,
      counts: out.counts,
      selected: out.selected ?? '',
    }).catch(() => {
      // Silently ignored
    });
  }, [location.pathname]);

  // Selection changes: lightweight polling comparison (avoids hooking into each
  // page's store subscriptions; selection changes are infrequent)
  const pollSelection = useCallback(() => {
    if (!activityReportEnabled()) return;
    const probe = resolvePageProbe(location.pathname);
    if (!probe) return;
    const out = probe.report();
    const sel = out?.selected ?? '';
    if (out && sel !== lastSelected.current) {
      lastSelected.current = sel;
      void reportPageContext({
        page: probe.page,
        summary: out.summary,
        counts: out.counts,
        selected: sel,
      }).catch(() => {});
    }
  }, [location.pathname]);

  useEffect(() => {
    clearTimers();
    if (!activityReportEnabled()) return;
    reportPageView(location.pathname);
    // Let page data load before the first summary report (one-tick initial delay)
    timersRef.current.t1 = window.setTimeout(reportSummary, INITIAL_DELAY_MS);
    timersRef.current.summary = window.setInterval(reportSummary, SUMMARY_INTERVAL_MS);
    timersRef.current.selection = window.setInterval(pollSelection, SELECTION_POLL_MS);
    return clearTimers;
  }, [location.pathname, clearTimers, reportSummary, pollSelection]);

  return null;
}
