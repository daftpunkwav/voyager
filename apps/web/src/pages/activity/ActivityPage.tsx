/**
 * @file ActivityPage
 * @description Activity page: the agent-operations log. A thin route shell
 * that mirrors the settings-section shell (glass card + h2) so the shared
 * ActivityFeed widget sits in the same surface as the model-settings tab;
 * the feed size is reported to the page-awareness provider, clearing the
 * stale count on failure.
 */

import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { useSearchParams } from 'react-router-dom';
import { ActivityFeed } from '@/components/activity/ActivityFeed';
import { rememberActivityFeedCount } from './provider';

export function ActivityPage() {
  const { t } = useTranslation('activity');
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
      <section className="settings-section glass-card glass-card--overview-outer">
        <h2>{t('page.title')}</h2>
        <ActivityFeed kind={kind} onKindChange={setKind} onLoaded={rememberActivityFeedCount} />
      </section>
    </div>
  );
}

export default ActivityPage;
