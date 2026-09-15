/**
 * @file ActivityPage
 * @description Activity page: replays the event feed with per-type summaries.
 *
 * Fetches events from /api/activity/feed and summarizes the most recent entries
 * by type, keeping everything the agent did visible, inspectable, and revocable
 * in the UI.
 *
 * Responsibilities:
 * - Fetch the kind-filtered event feed with manual retry
 * - Render summarized rows (bridge/feed summarize) with tone styling
 * - Report the loaded feed size to the page-awareness provider, clearing
 *   the stale count on failure
 */

import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { GlassCard } from '@/components/common/GlassCard';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState, EmptyStateIcons } from '@/components/common/EmptyState';
import { summarize, type FeedEvent } from '@/bridge/feed';
import { EventType } from '@/bridge/events';
import { fetchActivityFeed } from '@/bridge/activity';
import { extractErrorMessage } from '@/utils/errors';
import { rememberActivityFeedCount } from './provider';

/** Filter options; labels come from the activity:filter.* resources. */
const KIND_OPTIONS: Array<{ value: string; key: string }> = [
  { value: '', key: 'activity:filter.all' },
  { value: EventType.USER_MESSAGE, key: 'activity:filter.userMessage' },
  { value: EventType.AGENT_MESSAGE, key: 'activity:filter.agentMessage' },
  { value: EventType.TASK_PROGRESS, key: 'activity:filter.taskProgress' },
  { value: EventType.NOTE_CREATED, key: 'activity:filter.noteCreated' },
  { value: EventType.SOURCE_ADDED, key: 'activity:filter.sourceAdded' },
  { value: EventType.SETTINGS_CHANGED, key: 'activity:filter.settingsChanged' },
];

export function ActivityPage() {
  const { t } = useTranslation('activity');
  const [params, setParams] = useSearchParams();
  const kind = params.get('kind') ?? '';
  const [events, setEvents] = useState<FeedEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retryTick, setRetryTick] = useState(0);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    (async () => {
      try {
        const feed = await fetchActivityFeed(kind);
        if (!alive) return;
        setEvents(feed);
        // Report the feed size to the page-awareness provider once loaded; skip while loading or on failure
        rememberActivityFeedCount(feed.length);
      } catch (err) {
        if (alive) {
          setError(extractErrorMessage(err));
          rememberActivityFeedCount(null); // clear the stale count on failure
        }
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, [kind, retryTick]);

  const hasContent = !loading && !error && events.length > 0;

  return (
    <div className="activity-page page-scaffold">
      {hasContent && (
        <div className="activity-page__toolbar">
          <select
            className="filter-native-select"
            value={kind}
            onChange={(e) => {
              const v = e.target.value;
              if (v) setParams({ kind: v });
              else setParams({});
            }}
            aria-label={t('activity:filter.aria')}
          >
            {KIND_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {t(o.key)}
              </option>
            ))}
          </select>
        </div>
      )}

      {loading ? (
        <div className="page-scaffold__state">
          <LoadingSpinner label={t('activity:loading')} />
        </div>
      ) : error ? (
        <div className="page-scaffold__state">
          <EmptyState
            title={t('activity:error.title')}
            description={error}
            icon={EmptyStateIcons.activity}
            onRetry={() => setRetryTick((n) => n + 1)}
          />
        </div>
      ) : events.length === 0 ? (
        <div className="page-scaffold__state">
          <EmptyState
            title={t('activity:empty.title')}
            description={t('activity:empty.description')}
            icon={EmptyStateIcons.activity}
          />
        </div>
      ) : (
        <div className="page-scaffold__body">
          <GlassCard className="activity-card">
            <ul className="activity-list">
              {events.map((ev) => {
                const s = summarize(ev);
                return (
                  <li
                    key={ev.seq ?? `${ev.ts}-${ev.id}`}
                    className={`activity-row activity-row--${s.tone}`}
                  >
                    <span className="small mono">
                      {ev.ts ? new Date(ev.ts * 1000).toLocaleString() : ''}
                    </span>
                    <span className="activity-row__text">{s.text}</span>
                  </li>
                );
              })}
            </ul>
          </GlassCard>
        </div>
      )}
    </div>
  );
}

export default ActivityPage;
