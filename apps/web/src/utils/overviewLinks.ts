/**
 * @file overviewLinks
 * @description Maps overview activity items to their target routes.
 */

import type { ActivityItem } from '@/api/types';
import { routes } from '@/utils/routes';

/** Jump target for a recent-activity item (branching on its type). */
export function activityItemHref(item: ActivityItem): string {
  switch (item.type) {
    case 'import':
    case 'progress':
      return item.project_id ? routes.sourceRepo(item.project_id) : routes.sources;
    case 'note':
      return item.project_id ? routes.sourceRepo(item.project_id) : routes.notes;
    case 'agent':
    default:
      return routes.chat;
  }
}
