/**
 * @file RawLogView
 * @description The chat page's log tab: every recorded LLM round of the
 * current session, each showing the raw request transcript (the exact
 * messages the model received) and the raw response, verbatim. Data comes
 * from GET /api/chat/rawllm (via bridge/chatSend) backed by the trajectory
 * store.
 */

import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useChatStore } from '@/stores/chatStore';
import { fetchRawLlmRounds, type RawLlmRound } from '@/bridge/chatSend';

/** Newest rounds rendered. The endpoint returns every recorded round of the
 *  session with full verbatim bodies; a long session can total tens of MB and
 *  rendering it all as <pre> DOM freezes the tab. Older rounds stay recorded
 *  server-side — only the rendered window is capped. */
const RENDER_LIMIT = 50;

function pretty(raw: string): string {
  try {
    return JSON.stringify(JSON.parse(raw), null, 2);
  } catch {
    return raw; // non-JSON body: show as-is
  }
}

function RoundCard({ round }: { round: RawLlmRound }) {
  const { t } = useTranslation('chat');
  const [tab, setTab] = useState<'request' | 'response'>('request');
  const time = new Date(round.ts * 1000).toLocaleTimeString();
  // Memoized: the raw bodies can be large, and re-parsing on every render of
  // the card (e.g. the count-note state change above) is wasted work.
  const body = useMemo(
    () => pretty(tab === 'request' ? round.request : round.response),
    [tab, round.request, round.response]
  );
  return (
    <section className="chat-log__round">
      <div className="chat-log__head">
        <span className="chat-log__meta">
          {t('chat:trace.roundN', { n: round.round })} · {time}
        </span>
        <div className="chat-log__tabs" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'request'}
            className={`chat-log__tab${tab === 'request' ? ' is-active' : ''}`}
            onClick={() => setTab('request')}
          >
            {t('chat:rawlog.request')}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'response'}
            className={`chat-log__tab${tab === 'response' ? ' is-active' : ''}`}
            onClick={() => setTab('response')}
          >
            {t('chat:rawlog.response')}
          </button>
        </div>
      </div>
      <pre className="chat-log__body">{body}</pre>
    </section>
  );
}

export function RawLogView() {
  const { t } = useTranslation('chat');
  const activeId = useChatStore((s) => s.activeSessionId);
  const [page, setPage] = useState<{ rounds: RawLlmRound[]; total: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setPage(null);
    setError(null);
    fetchRawLlmRounds(activeId)
      .then((data) => {
        if (!cancelled) setPage(data);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [activeId]);

  const rounds = page?.rounds ?? null;
  // Newest-first render window: rounds arrive ascending, so the reversed tail
  // is the newest RENDER_LIMIT rounds. `beyond` counts what is not shown at
  // all: older than the backend page AND older than the render window.
  const visible = useMemo(
    () => (rounds ? [...rounds].reverse().slice(0, RENDER_LIMIT) : []),
    [rounds]
  );
  const beyond = Math.max(0, (page?.total ?? 0) - (rounds?.length ?? 0));

  if (error) return <div className="chat-log chat-log--empty">⚠ {error}</div>;
  if (page === null) {
    return <div className="chat-log chat-log--empty">{t('chat:rawlog.loading')}</div>;
  }
  if (rounds === null || rounds.length === 0) {
    return <div className="chat-log chat-log--empty">{t('chat:rawlog.empty')}</div>;
  }
  const hidden = rounds.length - visible.length + beyond;
  if (hidden > 0) {
    return (
      <div className="chat-log">
        <div className="chat-log__hidden small muted" role="note">
          {t('chat:rawlog.hiddenRounds', { n: hidden, shown: visible.length })}
        </div>
        {visible.map((r) => (
          <RoundCard key={`${r.run_id}-${r.round}-${r.ts}`} round={r} />
        ))}
      </div>
    );
  }
  return (
    <div className="chat-log">
      {visible.map((r) => (
        <RoundCard key={`${r.run_id}-${r.round}-${r.ts}`} round={r} />
      ))}
    </div>
  );
}
