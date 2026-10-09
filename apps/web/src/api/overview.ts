/**
 * @file overview.ts
 * @description Cross-domain overview aggregation (trending / recommended / recent notes).
 *
 * Each overview concept is approximated with existing live capabilities, and
 * this module is the single mapping point from raw backend rows onto the
 * overview row vocabulary (trending: search_remote_repos; recent notes:
 * list_notes + a sources name join). All functions return payloads directly,
 * without a {data} envelope.
 *
 * Responsibilities:
 * - Approximate overview concepts with live capabilities: trending via
 *   remote repo search, recommendations via list_repos, recent notes via
 *   list_notes (+ repo-name join)
 * - Keep the empty activity feed and the dormant scout-intro stream
 *   contract so later wiring only touches this file
 *
 * This module must not depend on UI-layer components.
 */

import { callCapability } from '@/bridge/client';
import type { TrendingRepo } from '@/api/types';

/** Trending window per period, expressed as a GitHub `pushed:` qualifier (days). */
const PERIOD_DAYS: Record<string, number> = { daily: 1, weekly: 7, monthly: 30 };
/** Trending grid size; the backend caps per_page at 30 anyway. */
const TRENDING_LIMIT = 12;

function isoDaysAgo(days: number): string {
  return new Date(Date.now() - days * 86_400_000).toISOString().slice(0, 10);
}

/** Raw search_remote_repos row (sources.modules.repo.github.search_repos). */
interface RemoteRepoRow {
  owner?: unknown;
  name?: unknown;
  url?: unknown;
  description?: unknown;
  stars?: unknown;
  language?: unknown;
}

/** Trending approximated by remote repo search (returns real data, no longer
 *  flagged as degraded). The capability contract is search_remote_repos(query,
 *  limit), so the period/language selectors are compiled into GitHub search
 *  qualifiers here, and rows are normalized onto the canonical TrendingRepo
 *  shape (the backend answers owner/name/url, the UI vocabulary is
 *  owner/repo/html_url). */
export async function listTrending(p?: {
  period?: string;
  language?: string;
}): Promise<TrendingRepo[]> {
  const days = PERIOD_DAYS[p?.period ?? 'weekly'] ?? 7;
  const query = ['stars:>100', `pushed:>${isoDaysAgo(days)}`];
  if (p?.language) query.push(`language:${p.language}`);
  const rows = await callCapability<RemoteRepoRow[]>('sources', 'search_remote_repos', {
    query: query.join(' '),
    limit: TRENDING_LIMIT,
  });
  const list = Array.isArray(rows) ? rows : [];
  return list.map((r) => {
    const owner = String(r.owner ?? '');
    const name = String(r.name ?? '');
    return {
      owner,
      repo: name,
      full_name: `${owner}/${name}`,
      description: String(r.description ?? ''),
      stars: Number(r.stars ?? 0),
      language: r.language ? String(r.language) : null,
      html_url: String(r.url ?? ''),
    };
  });
}

/** Activity feed: the backend has no dedicated activity entity yet, so this stays
 *  empty (the shell timeline consumes bridge/stream events instead). */
export function listActivities(): Promise<unknown[]> {
  return Promise.resolve([]);
}

/** Recommended approximated by in-library projects (list_repos). */
export function listRecommendedProjects(p?: { limit?: number }): Promise<unknown> {
  return callCapability('sources', 'list_repos', p ?? {});
}

/** Recent-note row in the consumer vocabulary. Backend list_notes rows carry
 *  source_id and epoch updated_ts; the overview card reads project_id /
 *  ISO updated_at and a display name joined from the sources repo list. */
export interface RecentNoteRow {
  id: string;
  title: string;
  project_id?: string;
  project_name?: string;
  updated_at: string;
}

/** Raw list_notes summary row (notes store _SUMMARY_COLS). */
interface NoteSummaryRow {
  id?: unknown;
  title?: unknown;
  source_id?: unknown;
  updated_ts?: unknown;
}

export async function listOverviewRecentNotes(p?: { limit?: number }): Promise<RecentNoteRow[]> {
  const rows = await callCapability<NoteSummaryRow[]>('notes', 'list_notes', p ?? {});
  const list = Array.isArray(rows) ? rows : [];
  // Display names come from the sources repo list; a sources failure must not
  // blank the notes card, so the join degrades to empty names (allSettled).
  const nameById = new Map<string, string>();
  const repos = await Promise.allSettled([callCapability('sources', 'list_repos', {})]);
  if (repos[0].status === 'fulfilled' && Array.isArray(repos[0].value)) {
    for (const r of repos[0].value as Record<string, unknown>[]) {
      nameById.set(String(r.id ?? ''), String(r.name ?? ''));
    }
  }
  return list.map((r) => {
    const projectId = String(r.source_id ?? '');
    const ts = Number(r.updated_ts ?? 0);
    return {
      id: String(r.id ?? ''),
      title: String(r.title ?? ''),
      project_id: projectId || undefined,
      project_name: projectId ? (nameById.get(projectId) ?? '') : '',
      updated_at: ts ? new Date(ts * 1000).toISOString() : '',
    };
  });
}

/** Scout intro stream (empty): the backend stream is not wired up, so
 *  TrendingSpotlight stays hidden when no events arrive. The contract is kept
 *  so wiring it up later only requires changing this function. */
export interface ScoutIntroEvent {
  event: string;
  data: Record<string, unknown>;
}

// Empty-stream contract kept for future wiring (nothing is yielded or awaited
// until the backend stream is connected), hence require-yield and require-await
// are disabled.
// eslint-disable-next-line require-yield, @typescript-eslint/require-await
export async function* streamTrendingScoutIntro(): AsyncGenerator<ScoutIntroEvent> {
  return;
}
