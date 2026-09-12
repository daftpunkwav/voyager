/**
 * @file types/system.ts
 * @description System / overview domain types: activity feed, GitHub trending,
 * recommended projects, recent overview notes.
 *
 * Split out of api/types.ts; pages and hooks still import from the
 * @/api/types barrel.
 */

import type { AgentId } from './agent';
import type { Project } from './sources';

// ---------- Activity / Trending ----------

export interface ActivityItem {
  id: string;
  actor: 'user' | 'agent' | 'system';
  type: string;
  payload: Record<string, unknown>;
  ts: number;
  trace_id?: string;
  project_id?: string;
  source_id?: string;
  session_id?: string;
  agent_id?: AgentId;
  title?: string;
  href?: string;
}

export interface TrendingRepo {
  full_name: string;
  owner: string;
  repo: string;
  description: string;
  stars: number;
  language: string | null;
  html_url: string;
  avatar_url?: string;
}

export type TrendingPeriod = 'daily' | 'weekly' | 'monthly';

export interface RecommendedProject {
  project: Project;
  reason: string;
  score: number;
}

export interface OverviewRecentNote {
  id: string;
  title: string;
  excerpt: string;
  updated_ts: number;
}
