/**
 * @file ActivityFeed
 * @description Shared activity stream widget: kind filter + fetch + summarized
 * list. Rendered by the standalone activity page and embedded in Settings;
 * the page reports the feed size onward via onLoaded (page-probe summary).
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { GlassCard } from '@/components/common/GlassCard';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState, EmptyStateIcons } from '@/components/common/EmptyState';
import { summarize, type FeedEvent } from '@/bridge/feed';
import { EventType } from '@/bridge/events';
import { fetchActivityFeed } from '@/bridge/activity';
import { extractErrorMessage } from '@/utils/errors';

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

interface ActivityFeedProps {
  /** Current kind filter ('' = all) */
  kind: string;
  onKindChange: (v: string) => void;
  /** Called after every fetch settles: feed size, or null while loading/failed. */
  onLoaded?: (count: number | null) => void;
}

export function ActivityFeed({ kind, onKindChange, onLoaded }: ActivityFeedProps) {
  const { t } = useTranslation('activity');
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
        onLoaded?.(feed.length);
      } catch (err) {
        if (alive) {
          setError(extractErrorMessage(err));
          onLoaded?.(null);
        }
      } finally {
        if (alive) setLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
    // onLoaded is expected to be stable (module fn / setState); excluded on purpose
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [kind, retryTick]);

  const hasContent = !loading && !error && events.length > 0;

  return (
    <>
      {hasContent && (
        <div className="activity-page__toolbar">
          <select
            className="filter-native-select"
            value={kind}
            onChange={(e) => onKindChange(e.target.value)}
            aria-label={t('filter.aria')}
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
          <LoadingSpinner label={t('loading')} />
        </div>
      ) : error ? (
        <div className="page-scaffold__state">
          <EmptyState
            title={t('error.title')}
            description={error}
            icon={EmptyStateIcons.activity}
            onRetry={() => setRetryTick((n) => n + 1)}
          />
        </div>
      ) : events.length === 0 ? (
        <div className="page-scaffold__state">
          <EmptyState
            title={t('empty.title')}
            description={t('empty.description')}
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
    </>
  );
}
