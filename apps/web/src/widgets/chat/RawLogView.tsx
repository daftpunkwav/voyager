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
  // Collapsed by default: the log tab is a scanning surface; bodies render
  // only for the round being inspected (large <pre>s add up fast).
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<'request' | 'response'>('request');
  const time = new Date(round.ts * 1000).toLocaleTimeString();
  // Memoized: the raw bodies can be large, and re-parsing them on every
  // parent-driven re-render of the card is wasted work.
  const body = useMemo(
    () => (open ? pretty(tab === 'request' ? round.request : round.response) : ''),
    [open, tab, round.request, round.response]
  );
  // A tab click on a collapsed card expands it into that tab; on an open card
  // it just switches panes (collapsing is the header toggle's job).
  const pickTab = (next: 'request' | 'response') => {
    setTab(next);
    setOpen(true);
  };
  return (
    <section className={`chat-log__round${open ? ' is-open' : ''}`}>
      <div className="chat-log__head">
        <button
          type="button"
          className="chat-log__toggle"
          aria-expanded={open}
          aria-label={t('chat:rawlog.toggle')}
          onClick={() => setOpen((v) => !v)}
        >
          <span className="chat-log__chevron" aria-hidden>
            {open ? '▾' : '▸'}
          </span>
          <span className="chat-log__meta">
            {t('chat:trace.roundN', { n: round.round })} · {time}
          </span>
        </button>
        <div className="chat-log__tabs" role="tablist">
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'request'}
            className={`chat-log__tab${tab === 'request' ? ' is-active' : ''}`}
            onClick={() => pickTab('request')}
          >
            {t('chat:rawlog.request')}
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'response'}
            className={`chat-log__tab${tab === 'response' ? ' is-active' : ''}`}
            onClick={() => pickTab('response')}
          >
            {t('chat:rawlog.response')}
          </button>
        </div>
      </div>
      {open ? <pre className="chat-log__body">{body}</pre> : null}
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
    if (!activeId) {
      // Legacy session-less view (sessions capability unavailable): the rawllm
      // API requires a session or run id, so fetching would 400 — show the
      // empty state instead of surfacing the backend error text.
      setPage({ rounds: [], total: 0 });
      return () => {
        cancelled = true;
      };
    }
    // Fetch exactly the rendered window: round bodies are verbatim transcripts
    // (tens of KB each), so pulling the backend's default 200-round page for a
    // 50-round render would transfer and JSON-parse 4x more than is shown.
    // `total` still reports the session's full count, so the hidden-rounds
    // note stays correct.
    fetchRawLlmRounds(activeId, RENDER_LIMIT)
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
  return (
    <div className="chat-log">
      {hidden > 0 ? (
        <div className="chat-log__hidden small muted" role="note">
          {t('chat:rawlog.hiddenRounds', { n: hidden, shown: visible.length })}
        </div>
      ) : null}
      {visible.map((r) => (
        <RoundCard key={`${r.run_id}-${r.round}-${r.ts}`} round={r} />
      ))}
    </div>
  );
}
