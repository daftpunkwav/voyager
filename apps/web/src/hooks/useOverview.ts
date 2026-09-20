/**
 * @file useOverview
 * @description Overview-page hooks: recommendations, recent notes, trending and the activity feed.
 *
 * Responsibilities:
 * - Query the four overview cards: recommendations, recent notes, trending
 *   (period/language keyed), and the activity feed
 * - Narrow payloads to the row shapes components consume
 */

import { useQuery } from '@tanstack/react-query';
import {
  listRecommendedProjects,
  listOverviewRecentNotes,
  listTrending,
  listActivities,
} from '@/api/overview';
import type { ActivityItem, TrendingRepo } from '@/api/types';

/** Recommendation row (components consume id/name/project_id/description/reason/stars). */
type RecommendRow = {
  id: string;
  name: string;
  owner?: string | null;
  project_id?: string;
  description?: string;
  reason?: string;
  stars?: number;
};

/** Recent-note row (components consume id/title/project_id/project_name/updated_at). */
type RecentNoteRow = {
  id: string;
  title: string;
  project_id?: string;
  project_name?: string;
  updated_at: string;
};

/** Overview - personalized agent recommendations. */
export function useRecommendedProjects(limit = 5) {
  return useQuery({
    queryKey: ['overview', 'recommendations', limit],
    queryFn: async () => (await listRecommendedProjects({ limit })) as RecommendRow[],
  });
}

/** Overview - recent notes (with project names). */
export function useOverviewRecentNotes(limit = 4) {
  return useQuery({
    queryKey: ['overview', 'recentNotes', limit],
    queryFn: async () => (await listOverviewRecentNotes({ limit })) as RecentNoteRow[],
  });
}

/** Overview - GitHub trending. */
export function useTrending(period: 'daily' | 'weekly' | 'monthly', language?: string) {
  return useQuery({
    queryKey: ['trending', period, language],
    queryFn: async () =>
      (await listTrending({ period, language })) as Array<
        TrendingRepo & { url?: string; rank?: number }
      >,
  });
}

/** Overview - activity feed. */
export function useActivities() {
  return useQuery({
    queryKey: ['activities'],
    queryFn: async () =>
      (await listActivities()) as Array<
        ActivityItem & { description?: string; created_at: string }
      >,
  });
}
