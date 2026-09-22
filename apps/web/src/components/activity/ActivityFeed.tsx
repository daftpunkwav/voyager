/**
 * @file ActivityFeed
 * @description Shared activity stream widget: kind filter + agent/session
 * attribution filters + fetch + summarized list. Rendered by the standalone
 * activity page and embedded in Settings; the page reports the feed size
 * onward via onLoaded (page-probe summary). Events stamped with a session
 * were caused by an agent turn (the invocation context carries it); unstamped
 * rows are manual (REST/UI) operations.
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { GlassCard } from '@/components/common/GlassCard';
import { GlassSelect } from '@/components/common/GlassSelect';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState, EmptyStateIcons } from '@/components/common/EmptyState';
import { summarize, type FeedEvent } from '@/bridge/feed';
import { EventType } from '@/bridge/events';
import { fetchActivityFeed } from '@/bridge/activity';
import { loadChatSessions } from '@/bridge/chatSend';
import { useChatStore } from '@/stores/chatStore';
import { extractErrorMessage } from '@/utils/errors';

/** Filter options; labels come from the activity:filter.* resources. */
const KIND_OPTIONS: Array<{ value: string; key: string }> = [
  { value: '', key: 'activity:filter.all' },
  { value: EventType.USER_MESSAGE, key: 'activity:filter.userMessage' },
  { value: EventType.AGENT_MESSAGE, key: 'activity:filter.agentMessage' },
  { value: EventType.TASK_PROGRESS, key: 'activity:filter.taskProgress' },
  { value: EventType.NOTE_CREATED, key: 'activity:filter.noteCreated' },
  { value: EventType.NOTE_DELETED, key: 'activity:filter.noteDeleted' },
  { value: EventType.NOTE_RESTORED, key: 'activity:filter.noteRestored' },
  { value: EventType.NOTE_PURGED, key: 'activity:filter.notePurged' },
  { value: EventType.SOURCE_ADDED, key: 'activity:filter.sourceAdded' },
  { value: EventType.SOURCE_REMOVED, key: 'activity:filter.sourceRemoved' },
  { value: EventType.SESSION_DELETED, key: 'activity:filter.sessionDeleted' },
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
  // Attribution filters: agent-only keeps chat-turn-stamped events, session
  // narrows to one originating session (implies agent). Local view state —
  // the kind filter is the parent's, these die with the mount.
  const [agentOnly, setAgentOnly] = useState(false);
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
        const feed = await fetchActivityFeed(kind, { agentOnly, session });
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
  }, [kind, agentOnly, session, retryTick]);

  // Keep the toolbar reachable while an attribution filter is active, or the
  // empty result state would leave no way to clear it
  const showToolbar = (!loading && !error) || agentOnly || session !== '';
  const sessionTitle = (sid: string): string => {
    const row = sessions.find((s) => s.session_id === sid);
    return row?.title || sid;
  };

  return (
    <>
      {showToolbar && (
        <div className="activity-page__toolbar">
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
            value={agentOnly ? 'agent' : ''}
            options={[
              { value: '', label: t('filter.scopeAll') },
              { value: 'agent', label: t('filter.scopeAgent') },
            ]}
            onChange={(v) => setAgentOnly(v === 'agent')}
            aria-label={t('filter.scopeAria')}
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
                const origin = String(ev.payload?.session ?? '');
                return (
                  <li
                    key={ev.seq ?? `${ev.ts}-${ev.id}`}
                    className={`activity-row activity-row--${s.tone}`}
                  >
                    <span className="small mono">
                      {ev.ts ? new Date(ev.ts * 1000).toLocaleString() : ''}
                    </span>
                    <span className="activity-row__text">{s.text}</span>
                    {origin !== '' && (
                      <span className="small muted">
                        {t('fromSession', { title: sessionTitle(origin) })}
                      </span>
                    )}
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
