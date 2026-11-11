/**
 * @file RawLogRoundCard
 * @description One recorded raw LLM round: the round header (number,
 * timestamp, expand toggle) plus the tab bar that switches between the wire
 * request body, the request the model received, and the raw response.
 *
 * Responsibilities:
 * - Render the round header and its expand toggle
 * - Switch between the recorded bodies of the round
 * - Show the selected body verbatim (pretty-printed when it is JSON)
 *
 * Constraints:
 * - Collapsed by default: the log tab is a scanning surface, bodies render
 *   only for the round being inspected (large <pre>s add up fast)
 * - A tab click on a collapsed card expands it into that tab; on an open card
 *   it just switches panes (collapsing is the header toggle's job)
 */

import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { RawLlmRound } from '@/bridge/chatSend';
import { RawLogRoundTabs, type RawLogRoundTab } from './RawLogRoundTabs';

/** Pretty-print a recorded body; non-JSON bodies are shown as-is. */
function pretty(raw: string): string {
  try {
    return JSON.stringify(JSON.parse(raw), null, 2);
  } catch {
    return raw; // non-JSON body: show as-is
  }
}

/** The recorded body of one tab of a round. */
function roundBody(round: RawLlmRound, tab: RawLogRoundTab): string {
  if (tab === 'request') return pretty(round.request);
  if (tab === 'response') return pretty(round.response);
  return round.wire_request ? pretty(round.wire_request) : '';
}

export function RawLogRoundCard({ round }: { round: RawLlmRound }) {
  const { t } = useTranslation('chat');
  const [open, setOpen] = useState(false);
  const hasWire = !!round.wire_request;
  const [tab, setTab] = useState<RawLogRoundTab>(hasWire ? 'wire' : 'request');
  const time = new Date(round.ts * 1000).toLocaleTimeString();
  // Memoized: the raw bodies can be large, and re-parsing them on every
  // parent-driven re-render of the card is wasted work.
  const body = useMemo(() => (open ? roundBody(round, tab) : ''), [open, round, tab]);
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
        <RawLogRoundTabs
          active={tab}
          hasWire={hasWire}
          onPick={(next) => {
            setTab(next);
            setOpen(true);
          }}
        />
      </div>
      {open ? <pre className="chat-log__body">{body}</pre> : null}
    </section>
  );
}
