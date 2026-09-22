/**
 * @file ActivityFeed
 * @description Shared widget for the agent-operations log: operation-type and
 * session filters + fetch + summarized list. Rendered by the standalone
 * activity page and embedded in Settings; the page reports the feed size
 * onward via onLoaded (page-probe summary). The feed is agent-scoped by
 * contract — rows are changes the agent made to the system.
 */

import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { GlassSelect } from '@/components/common/GlassSelect';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState, EmptyStateIcons } from '@/components/common/EmptyState';
import { summarize, type FeedEvent } from '@/bridge/feed';
import { EventType } from '@/bridge/events';
import { fetchActivityFeed } from '@/bridge/activity';
import { loadChatSessions } from '@/bridge/chatSend';
import { useChatStore } from '@/stores/chatStore';
import { extractErrorMessage } from '@/utils/errors';

/** Operation-type filter options; labels come from the activity:filter.* resources. */
const KIND_OPTIONS: Array<{ value: string; key: string }> = [
  { value: '', key: 'activity:filter.all' },
  { value: EventType.NOTE_CREATED, key: 'activity:filter.noteCreated' },
  { value: EventType.NOTE_EDITED, key: 'activity:filter.noteEdited' },
  { value: EventType.NOTE_DELETED, key: 'activity:filter.noteDeleted' },
  { value: EventType.NOTE_RESTORED, key: 'activity:filter.noteRestored' },
  { value: EventType.NOTE_PURGED, key: 'activity:filter.notePurged' },
  { value: EventType.SOURCE_ADDED, key: 'activity:filter.sourceAdded' },
  { value: EventType.SOURCE_REMOVED, key: 'activity:filter.sourceRemoved' },
  { value: EventType.AGENT_STEP, key: 'activity:filter.fileWrite' },
  { value: EventType.SETTINGS_CHANGED, key: 'activity:filter.settingsChanged' },
  { value: EventType.SESSION_DELETED, key: 'activity:filter.sessionDeleted' },
];

/** HH:MM:SS for today's rows, M/D HH:MM once the day has passed: keeps the
 *  time column narrow without repeating the full date on every row. */
function formatRowTime(ts: number, locale: string): string {
  const date = new Date(ts * 1000);
  const now = new Date();
  const sameDay =
    date.getFullYear() === now.getFullYear() &&
    date.getMonth() === now.getMonth() &&
    date.getDate() === now.getDate();
  const time = date.toLocaleTimeString(locale, {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
  if (sameDay) return time;
  const day = date.toLocaleDateString(locale, { month: 'numeric', day: 'numeric' });
  return `${day} ${time.slice(0, 5)}`;
}

interface ActivityFeedProps {
  /** Current operation-type filter ('' = all operations) */
  kind: string;
  onKindChange: (v: string) => void;
  /** Called after every fetch settles: feed size, or null while loading/failed. */
  onLoaded?: (count: number | null) => void;
}

export function ActivityFeed({ kind, onKindChange, onLoaded }: ActivityFeedProps) {
  const { t, i18n } = useTranslation('activity');
  const [events, setEvents] = useState<FeedEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retryTick, setRetryTick] = useState(0);
  const [session, setSession] = useState('');
  const sessions = useChatStore((s) => s.sessions);

  // The session dropdown reads the chat store's list; on the settings page no
  // chat view may have populated it yet, so fetch once (failure = empty list).
  useEffect(() => {
    if (sessions.length === 0) {
      loadChatSessions().catch(() => {});
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    (async () => {
      try {
        const feed = await fetchActivityFeed(kind, session);
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
  }, [kind, session, retryTick]);

  const sessionTitle = useMemo(() => {
    const byId = new Map(sessions.map((s) => [s.session_id, s.title] as const));
    return (sid: string): string => byId.get(sid) || sid;
  }, [sessions]);

  return (
    <div className="activity-feed">
      <div className="activity-feed__head">
        <span className="activity-feed__label">{t('feed.label')}</span>
        <span className="activity-feed__count">{loading ? '…' : events.length}</span>
        <div className="activity-feed__filters">
          {/* A real select (not the projects page's invisible overlay): the
              invisible absolute-position variant used here before rendered as
              a full-bleed native blue dropdown. */}
          <GlassSelect
            size="sm"
            value={kind}
            options={KIND_OPTIONS.map((o) => ({ value: o.value, label: t(o.key) }))}
            onChange={(v) => onKindChange(v)}
            aria-label={t('filter.aria')}
          />
          <GlassSelect
            size="sm"
            value={session}
            options={[
              { value: '', label: t('filter.sessionAll') },
              ...sessions.map((s) => ({
                value: s.session_id,
                label: s.title || s.session_id,
              })),
            ]}
            onChange={(v) => setSession(v)}
            aria-label={t('filter.sessionAria')}
          />
        </div>
      </div>

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
        <ul className="activity-feed__list">
          {events.map((ev) => {
            const s = summarize(ev);
            const origin = String(ev.payload?.session ?? '');
            return (
              <li
                key={ev.seq ?? `${ev.ts}-${ev.id}`}
                className={`activity-row activity-row--${s.tone}`}
              >
                <span className="activity-row__time mono">
                  {ev.ts ? formatRowTime(ev.ts, i18n.language) : ''}
                </span>
                <span className="activity-row__text">{s.text}</span>
                {origin !== '' && (
                  <span className="activity-row__origin">
                    {t('fromSession', { title: sessionTitle(origin) })}
                  </span>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
