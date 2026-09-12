/**
 * @file activity.ts
 * @description Behavior reporting: page_view fires on each route change.
 *
 * privacy.activity_report=false is a hard kill switch (full silence); every
 * failure is swallowed so reporting never disturbs the main flow. In-page
 * summary/selection reporting is not routed through this file — widgets/
 * PageProbe goes via reportPageContext.
 *
 * Responsibilities:
 * - Read the privacy.activity_report switch at init and refresh it on
 *   settings.changed
 * - Fire page_view reports over POST /api/activity on route changes
 * - Fetch the activity feed replay (kind-filtered) for the activity page
 * - Swallow every reporting failure so the main flow is never disturbed
 *
 * This module must not depend on UI-layer components.
 */

import { callCapability } from './client';
import type { FeedEvent } from './feed';
import { backendUnreachable } from '@/utils/errors';

export type ActivityKind = 'page_view' | 'pointer' | 'selection' | 'manual';

let enabled = true;

/** Read the privacy switch once at init; settings changes refresh it via the settings.changed event. */
export function setActivityReportEnabled(v: boolean): void {
  enabled = v;
}

export function activityReportEnabled(): boolean {
  return enabled;
}

export async function initActivityReport(): Promise<void> {
  try {
    const item = await callCapability<{ value: boolean }>('settings', 'get_setting', {
      key: 'privacy.activity_report',
    });
    enabled = item.value !== false;
  } catch {
    enabled = true; // Unreadable defaults to on (reporting is opt-out by default)
  }
}

/** page_view: no throttling — fires on every route change. */
export function reportPageView(page: string): void {
  if (!enabled) return;
  reportActivity({ kind: 'page_view', page });
}

async function reportActivity(body: {
  kind: ActivityKind;
  page: string;
  detail?: Record<string, unknown>;
}): Promise<void> {
  try {
    await fetch('/api/activity', {
      method: 'POST',
      credentials: 'include',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  } catch {
    // Silent: reporting must never disturb the main flow
  }
}

/** Activity page replay: reads the event stream; non-2xx throws with the backend envelope message. */
export async function fetchActivityFeed(kind: string): Promise<FeedEvent[]> {
  const url = new URL('/api/activity/feed', window.location.origin);
  if (kind) url.searchParams.set('kind', kind);
  const resp = await fetch(url.toString(), { credentials: 'include' });
  if (!resp.ok) {
    // Prefer the message from the backend JSON envelope; without one (e.g. the dev
    // proxy returning 500 while the backend is down) fall back to a network hint
    const body = (await resp.json().catch(() => null)) as {
      error?: { message?: string };
    } | null;
    throw new Error(body?.error?.message ?? backendUnreachable());
  }
  const body = (await resp.json()) as { events?: FeedEvent[]; items?: FeedEvent[] };
  return body.events ?? body.items ?? [];
}
