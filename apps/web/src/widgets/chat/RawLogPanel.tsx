/**
 * @file RawLogPanel
 * @description Right-hand drawer showing the raw LLM request transcript and
 * response of one trace round, fetched from /api/chat/rawllm. Opened from a
 * round block's 原始 button; state lives in chatStore so the deeply nested
 * trace rows never thread callbacks through the tree.
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useChatStore } from '@/stores/chatStore';

interface RawRound {
  run_id: string;
  round: number;
  session: string;
  ts: number;
  request: string;
  response: string;
}

interface RoundSummary {
  round: number;
  ts: number;
  request_bytes: number;
  response_bytes: number;
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(2)} MB`;
}

function pretty(raw: string): string {
  try {
    return JSON.stringify(JSON.parse(raw), null, 2);
  } catch {
    return raw; // truncated or non-JSON body: show as-is
  }
}

export function RawLogPanel() {
  const { t } = useTranslation('chat');
  const rawLog = useChatStore((s) => s.rawLog);
  const setRawLog = useChatStore((s) => s.setRawLog);
  const [rounds, setRounds] = useState<RoundSummary[]>([]);
  const [detail, setDetail] = useState<RawRound | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<'request' | 'response'>('request');

  useEffect(() => {
    if (!rawLog) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    const q = new URLSearchParams({ run_id: rawLog.runId, round: String(rawLog.round) });
    fetch(`/api/chat/rawllm?${q.toString()}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((data: { rounds?: RoundSummary[]; round?: RawRound | null }) => {
        if (cancelled) return;
        setRounds(data.rounds ?? []);
        setDetail(data.round ?? null);
        if (!data.round && !(data.rounds ?? []).length) setError(t('chat:rawlog.empty'));
      })
      .catch((err: Error) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [rawLog, t]);

  if (!rawLog) return null;
  const body = detail ? pretty(tab === 'request' ? detail.request : detail.response) : '';

  return (
    <aside className="chat-rawlog" role="complementary" aria-label={t('chat:rawlog.title')}>
      <div className="chat-rawlog__head">
        <span className="chat-rawlog__title">
          {t('chat:rawlog.title')}
          {rawLog.round > 0 ? ` · ${t('chat:trace.roundN', { n: rawLog.round })}` : ''}
        </span>
        <button
          type="button"
          className="chat-rawlog__close"
          aria-label={t('chat:rawlog.close')}
          onClick={() => setRawLog(null)}
        >
          ✕
        </button>
      </div>
      {loading ? (
        <div className="chat-rawlog__note small muted">{t('chat:rawlog.loading')}</div>
      ) : null}
      {!loading && error ? <div className="chat-rawlog__note small">⚠ {error}</div> : null}
      {!loading && detail ? (
        <>
          <div className="chat-rawlog__tabs" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={tab === 'request'}
              className={`chat-rawlog__tab${tab === 'request' ? ' is-active' : ''}`}
              onClick={() => setTab('request')}
            >
              {t('chat:rawlog.request')}
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={tab === 'response'}
              className={`chat-rawlog__tab${tab === 'response' ? ' is-active' : ''}`}
              onClick={() => setTab('response')}
            >
              {t('chat:rawlog.response')}
            </button>
          </div>
          <pre className="chat-rawlog__body">{body}</pre>
        </>
      ) : null}
      {!loading && !detail && rounds.length > 0 ? (
        <ul className="chat-rawlog__rounds">
          {rounds.map((r) => (
            <li key={r.round}>
              <button
                type="button"
                onClick={() => setRawLog({ runId: rawLog.runId, round: r.round })}
              >
                {t('chat:trace.roundN', { n: r.round })} · {formatBytes(r.request_bytes)} →{' '}
                {formatBytes(r.response_bytes)}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </aside>
  );
}
