/**
 * @file ActivityPage
 * @description Activity page: replays the event feed with per-type summaries.
 * A thin route shell around the shared ActivityFeed widget; the feed size is
 * reported to the page-awareness provider, clearing the stale count on failure.
 */

import { useCallback } from 'react';
import { useSearchParams } from 'react-router-dom';
import { ActivityFeed } from '@/components/activity/ActivityFeed';
import { rememberActivityFeedCount } from './provider';

export function ActivityPage() {
  const [params, setParams] = useSearchParams();
  const kind = params.get('kind') ?? '';
  const setKind = useCallback(
    (v: string) => {
      if (v) setParams({ kind: v });
      else setParams({});
    },
    [setParams]
  );

  return (
    <div className="activity-page page-scaffold">
      <ActivityFeed kind={kind} onKindChange={setKind} onLoaded={rememberActivityFeedCount} />
    </div>
  );
}

export default ActivityPage;
