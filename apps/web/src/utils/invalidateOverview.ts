/**
 * @file invalidateOverview
 * @description Overview-related React Query cache keys and a bulk invalidation
 * helper to call after user mutations.
 */

import type { QueryClient } from '@tanstack/react-query';

/** React Query cache keys used by the overview page (invalidated together after mutations). */
export const overviewQueryKeys = {
  activities: ['activities'] as const,
  recentNotes: (limit: number) => ['overview', 'recentNotes', limit] as const,
  recommendations: (limit: number) => ['overview', 'recommendations', limit] as const,
  userProfile: ['userProfile'] as const,
  projectStats: ['projectStats'] as const,
};

/** Refresh overview data after user actions (trending excluded; updated by the backend on a schedule). */
export function invalidateOverviewQueries(qc: QueryClient) {
  return Promise.all([
    qc.invalidateQueries({ queryKey: overviewQueryKeys.activities }),
    qc.invalidateQueries({ queryKey: ['overview', 'recentNotes'] }),
    qc.invalidateQueries({ queryKey: ['overview', 'recommendations'] }),
    qc.invalidateQueries({ queryKey: overviewQueryKeys.userProfile }),
    qc.invalidateQueries({ queryKey: overviewQueryKeys.projectStats }),
  ]);
}
