/**
 * @file overview.ts
 * @description Cross-domain overview aggregation (trending / recommended / recent notes).
 *
 * Each overview concept is approximated with an existing live capability.
 * All functions return payloads directly, without a {data} envelope.
 *
 * Responsibilities:
 * - Approximate overview concepts with live capabilities: trending via
 *   remote repo search, recommendations via list_repos, recent notes via
 *   list_notes
 * - Keep the empty activity feed and the dormant scout-intro stream
 *   contract so later wiring only touches this file
 *
 * This module must not depend on UI-layer components.
 */

import { callCapability, unwrapDataField } from '@/bridge/client';

/** Trending approximated by remote repo search (returns real data, no longer flagged as degraded). */
export function listTrending(p?: { period?: string; language?: string }): Promise<unknown> {
  return callCapability(
    'sources',
    'search_remote_repos',
    (p ?? {}) as Record<string, unknown>
  ).then(unwrapDataField);
}

/** Activity feed: the backend has no dedicated activity entity yet, so this stays
 *  empty (the shell timeline consumes bridge/stream events instead). */
export function listActivities(): Promise<unknown[]> {
  return Promise.resolve([]);
}

/** Recommended approximated by in-library projects (list_repos). */
export function listRecommendedProjects(p?: { limit?: number }): Promise<unknown> {
  return callCapability('sources', 'list_repos', p ?? {}).then(unwrapDataField);
}

export function listOverviewRecentNotes(p?: { limit?: number }): Promise<unknown> {
  return callCapability('notes', 'list_notes', p ?? {}).then(unwrapDataField);
}

/** Scout intro stream (empty): the backend stream is not wired up, so
 *  TrendingSpotlight stays hidden when no events arrive. The contract is kept
 *  so wiring it up later only requires changing this function. */
export interface ScoutIntroEvent {
  event: string;
  data: Record<string, unknown>;
}

// Empty-stream contract kept for future wiring (nothing is yielded until the
// backend stream is connected), hence require-yield is disabled
// eslint-disable-next-line require-yield
export async function* streamTrendingScoutIntro(): AsyncGenerator<ScoutIntroEvent> {
  return;
}
