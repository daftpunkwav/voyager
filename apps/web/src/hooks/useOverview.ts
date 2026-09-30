/**
 * @file useOverview
 * @description Overview-page hooks: recommendations, recent notes, trending and the activity feed.
 *
 * Responsibilities:
 * - Query the four overview cards: recommendations, recent notes, trending
 *   (period/language keyed), and the activity feed
 * - Row-shape mapping lives in api/overview (the single mapping point);
 *   this hook only narrows the list defaults
 */

import { useQuery } from '@tanstack/react-query';
import {
  listRecommendedProjects,
  listOverviewRecentNotes,
  listTrending,
  listActivities,
} from '@/api/overview';
import type { ActivityItem } from '@/api/types';

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
    queryFn: () => listOverviewRecentNotes({ limit }),
  });
}

/** Overview - GitHub trending. */
export function useTrending(period: 'daily' | 'weekly' | 'monthly', language?: string) {
  return useQuery({
    queryKey: ['trending', period, language],
    queryFn: () => listTrending({ period, language }),
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
