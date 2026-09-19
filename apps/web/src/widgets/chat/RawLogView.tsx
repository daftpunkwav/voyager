/**
 * @file RawLogView
 * @description The chat page's log tab: every recorded LLM round of the
 * current session, each showing the raw request transcript (the exact
 * messages the model received) and the raw response, verbatim. Data comes
 * from GET /api/chat/rawllm (via bridge/chatSend) backed by the trajectory
 * store.
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useChatStore } from '@/stores/chatStore';
import { fetchRawLlmRounds, type RawLlmRound } from '@/bridge/chatSend';

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
  const body = pretty(tab === 'request' ? round.request : round.response);
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
  const [rounds, setRounds] = useState<RawLlmRound[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setRounds(null);
    setError(null);
    fetchRawLlmRounds(activeId)
      .then((rows) => {
        if (!cancelled) setRounds(rows);
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      });
    return () => {
      cancelled = true;
    };
  }, [activeId]);

  if (error) return <div className="chat-log chat-log--empty">⚠ {error}</div>;
  if (rounds === null) {
    return <div className="chat-log chat-log--empty">{t('chat:rawlog.loading')}</div>;
  }
  if (rounds.length === 0) {
    return <div className="chat-log chat-log--empty">{t('chat:rawlog.empty')}</div>;
  }
  return (
    <div className="chat-log">
      {[...rounds].reverse().map((r) => (
        <RoundCard key={`${r.run_id}-${r.round}-${r.ts}`} round={r} />
      ))}
    </div>
  );
}
