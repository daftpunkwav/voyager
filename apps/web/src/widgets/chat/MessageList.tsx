/**
 * @file MessageList
 * @description Renders the chat message stream as a mainstream-agent-style
 * timeline: user bubbles, plain agent output (no chrome), and inline execution
 * traces between them — a closed turn renders its collapsed trail right above
 * the answer it produced, the live turn's trace sits under the newest user
 * message and auto-collapses when output text starts streaming.
 *
 * Shared by the chat page and the persistent floating window; lives in the
 * widgets layer so page-private components are never depended on in reverse.
 *
 * Responsibilities:
 * - Render user / agent messages with sanitized Markdown and highlighting
 * - Render inline turn traces (closed trails + live trace), system notices
 *   and the streaming indicator
 * - Load older history on scroll-to-top (backward paging), keeping the
 *   viewport anchored while rows are prepended
 * - Expand note artifact cards inline with on-demand note fetches
 */

import { useCallback, useEffect, useLayoutEffect, useRef, useState, Fragment } from 'react';
import { useNavigate } from 'react-router-dom';
import { useUIStore } from '@/stores/uiStore';
import { flushSync } from 'react-dom';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { type ChatMessage, type NoteArtifact, useChatStore } from '@/stores/chatStore';
import { fetchChatHistoryBefore, loadChatSessions, loadSessionTimeline } from '@/bridge/chatSend';
import { ServiceError } from '@/bridge/client';
import { forkSession, rateTurn, setActiveSession } from '@/api/agent';
import { getNote } from '@/api/notes';
import { extractErrorMessage } from '@/utils/errors';
import { routes } from '@/utils/routes';
import { ChatMarkdown } from '@/widgets/chat/ChatMarkdown';
import { ClosedTurnTrace, LiveTurnTrace } from '@/widgets/chat/TurnTrace';
import { i18n } from '@/i18n';
/** Scroll-top distance that arms the backward-history load. */
const LOAD_TRIGGER_PX = 80;

/** Follow live-trace growth only when the viewport is this close to the bottom. */
const FOLLOW_MARGIN_PX = 240;

/** Nearest scroll container around this element, INCLUDING the element itself:
 *  on the chat page the scroller is .chat-stream itself (ancestors are
 *  overflow:hidden), inside the floating window the stream's overflow is
 *  visible and .float-panel__body does the scrolling. */
function getScrollParent(node: HTMLElement): HTMLElement | null {
  let cur: HTMLElement | null = node;
  while (cur) {
    const oy = getComputedStyle(cur).overflowY;
    if (oy === 'auto' || oy === 'scroll') return cur;
    cur = cur.parentElement;
  }
  return null;
}

/** One entry of the unified conversation timeline: chat messages and note
 *  artifacts interleaved by their event seq, so receipts (e.g. "note
 *  created") stay attached to the turn that produced them instead of
 *  stacking at the stream tail. */
type TimelineItem =
  | { kind: 'msg'; seq: number; msg: ChatMessage }
  | { kind: 'artifact'; seq: number; artifact: NoteArtifact };

/** Note receipts are emitted while the tools run, i.e. BEFORE the reply that
 *  produced them; the reply reads better with the results under it, so
 *  artifacts produced inside a turn are re-parented to follow that turn's
 *  agent message. Artifacts with no reply yet stay in seq order at the tail. */
function reParentArtifacts(merged: TimelineItem[]): TimelineItem[] {
  const out: TimelineItem[] = [];
  for (const item of merged) {
    if (item.kind === 'msg') {
      out.push(item);
      continue;
    }
    // Insert after the newest message with seq <= the artifact's own seq
    // (its turn's closing answer); already-placed artifacts below the scan
    // position keep their relative order. No host message yet -> tail.
    let at = out.length;
    let lastArtifactEnd = out.length;
    let hit = false;
    for (let i = out.length - 1; i >= 0; i--) {
      const placed = out[i];
      if (placed.kind === 'artifact') {
        lastArtifactEnd = i + 1;
        continue;
      }
      if (placed.seq <= item.seq) {
        at = i + 1;
        hit = true;
        break;
      }
    }
    out.splice(hit ? at : Math.min(at, lastArtifactEnd), 0, item);
  }
  return out;
}

function mergeTimeline(messages: ChatMessage[], artifacts: NoteArtifact[]): TimelineItem[] {
  const items: TimelineItem[] = [
    ...messages.map((m) => ({ kind: 'msg' as const, seq: m.seq, msg: m })),
    ...artifacts.map((a) => ({ kind: 'artifact' as const, seq: a.seq, artifact: a })),
  ];
  // Both inputs ascend already; a merge-sort keeps that order stable.
  const out: TimelineItem[] = [];
  let i = 0;
  let j = 0;
  while (i < messages.length && j < artifacts.length) {
    if (messages[i].seq <= artifacts[j].seq) out.push(items[i++]);
    else out.push(items[messages.length + j++]);
  }
  while (i < messages.length) out.push(items[i++]);
  while (j < artifacts.length) out.push(items[messages.length + j++]);
  return reParentArtifacts(out);
}

export function MessageList() {
  const { t } = useTranslation('chat');
  const messages = useChatStore((s) => s.messages);
  const thinking = useChatStore((s) => s.thinking);
  const streaming = useChatStore((s) => s.streaming);
  const artifacts = useChatStore((s) => s.artifacts);
  const trails = useChatStore((s) => s.trails);
  const steps = useChatStore((s) => s.steps);
  const historyLoading = useChatStore((s) => s.historyLoading);
  const streamRef = useRef<HTMLDivElement>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const firstSeqRef = useRef<number | null>(null);
  const anchoredRef = useRef(false);

  // Pre-paint anchor: the first time history lands, pin the viewport to the
  // newest message instantly (useLayoutEffect runs before the browser paints).
  // An animated scroll from the top would make the user watch the whole
  // history fly by on every refresh.
  useLayoutEffect(() => {
    if (anchoredRef.current || messages.length === 0) return;
    const scroller = streamRef.current ? getScrollParent(streamRef.current) : null;
    if (!scroller) return;
    anchoredRef.current = true;
    scroller.scrollTop = scroller.scrollHeight;
  }, [messages.length]);

  const loadOlder = useCallback(async () => {
    const el = streamRef.current;
    const scroller = el ? getScrollParent(el) : null;
    const store = useChatStore.getState();
    if (!scroller || store.historyLoading || !store.hasMoreHistory) return;
    const oldest = store.messages.find((m) => m.seq > 0);
    if (!oldest) return;
    store.setHistoryLoading(true);
    const prevHeight = scroller.scrollHeight;
    const prevTop = scroller.scrollTop;
    const prevCount = store.messages.length;
    try {
      const page = await fetchChatHistoryBefore(oldest.seq);
      // Commit the prepended rows synchronously, then restore the scroll
      // offset before the browser paints: the viewport stays anchored on the
      // messages the user was reading instead of jumping
      flushSync(() => {
        useChatStore.getState().prependHistory(page.messages, page.hasMore);
      });
      const state = useChatStore.getState();
      if (state.messages.length === prevCount) {
        // The page held only duplicates: nothing new exists in that direction,
        // stop offering the load (an unanchored retry loop would never end)
        state.setHistoryLoading(false);
        useChatStore.setState({ hasMoreHistory: false });
        return;
      }
      // Restore the scroll offset before the browser paints: the viewport stays
      // anchored on the messages the user was reading instead of jumping.
      // scroll-behavior is instant by default (.chat-stream has no smooth CSS).
      scroller.scrollTop = scroller.scrollHeight - prevHeight + prevTop;
      // Content may still be shorter than the viewport (scrollTop pinned at 0,
      // no further scroll events): keep filling until the list is scrollable
      if (scroller.scrollTop <= LOAD_TRIGGER_PX && state.hasMoreHistory) {
        void loadOlder();
      }
    } catch {
      const state = useChatStore.getState();
      state.setHistoryLoading(false);
      state.addSystem(i18n.t('chat:history.loadOlderFailed'));
    }
  }, []);

  useEffect(() => {
    const el = streamRef.current;
    if (!el) return;
    const scroller = getScrollParent(el);
    if (!scroller) return;
    const onScroll = () => {
      if (scroller.scrollTop > LOAD_TRIGGER_PX) return;
      void loadOlder();
    };
    scroller.addEventListener('scroll', onScroll, { passive: true });
    return () => scroller.removeEventListener('scroll', onScroll);
  }, [loadOlder]);

  const firstSeq = messages.length ? messages[0].seq : null;

  useEffect(() => {
    const prev = firstSeqRef.current;
    firstSeqRef.current = firstSeq;
    // A prepended older page lowers the first seq; the loader anchors the
    // viewport itself, so only tail growth (new messages) scrolls to bottom.
    // Streaming deltas are intentionally absent here: per-delta smooth
    // scrolling reads as teleporting; growth follow-up lives in the effect
    // below and only fires when the user is already near the bottom.
    if (prev !== null && firstSeq !== null && firstSeq < prev) return;
    const reduce =
      typeof window !== 'undefined' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    bottomRef.current?.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'end' });
  }, [firstSeq, messages.length, thinking, artifacts.length]);

  // Trace growth and streaming text follow the output only when the user is
  // already near the bottom; reading history mid-turn is never yanked back.
  useEffect(() => {
    const el = streamRef.current;
    const scroller = el ? getScrollParent(el) : null;
    if (!scroller) return;
    const distance = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight;
    if (distance > FOLLOW_MARGIN_PX) return;
    bottomRef.current?.scrollIntoView({ behavior: 'auto', block: 'end' });
  }, [steps.length, streaming]);

  // Closed trails keyed by their closing message seq: the trace renders right
  // above the answer it produced.
  const trailBySeq = new Map(trails.map((tr) => [tr.msgSeq, tr]));
  // An interrupted turn closes under a synthetic negative key (no closing
  // message); keep its trace visible at the tail while that turn is the newest.
  const tailTrail = trails.length ? trails[trails.length - 1] : null;
  const lastMsg = messages[messages.length - 1];
  const showInterrupted =
    !thinking && steps.length === 0 && !!tailTrail && tailTrail.msgSeq < 0
      ? !lastMsg || (lastMsg.role === 'user' && tailTrail.userText === lastMsg.content)
      : false;

  return (
    <div className="chat-stream" ref={streamRef}>
      {historyLoading ? (
        <div className="chat-history-loader small muted" role="status">
          {t('chat:history.loadingOlder')}
        </div>
      ) : null}
      {(() => {
        let lastUser = '';
        return mergeTimeline(messages, artifacts).map((item) => {
          if (item.kind === 'artifact') {
            return <NoteArtifactCard key={`a${item.seq}`} artifact={item.artifact} />;
          }
          const m = item.msg;
          if (m.role === 'user') lastUser = m.content;
          const subject = lastUser;
          const trail = m.role === 'agent' ? trailBySeq.get(m.seq) : undefined;
          return (
            <Fragment key={`${m.seq ?? `local-${m.ts ?? item.seq}`}-${m.role}`}>
              {trail ? <ClosedTurnTrace steps={trail.steps} finalText={m.content} /> : null}
              <Bubble msg={m} subject={subject} />
            </Fragment>
          );
        });
      })()}
      <LiveTurnTrace />
      {showInterrupted && tailTrail ? <ClosedTurnTrace steps={tailTrail.steps} /> : null}
      {/* Streaming text renders inside the live trace's round block: the trace
          IS the execution record, and the closing agent.message is the only
          thing that ever renders as the final answer. */}
      <div ref={bottomRef} />
    </div>
  );
}

function Bubble({ msg, subject }: { msg: ChatMessage; subject: string }) {
  const { t } = useTranslation('chat');
  const addToast = useUIStore((s) => s.addToast);
  const [copied, setCopied] = useState(false);
  const [rateOpen, setRateOpen] = useState(false);
  if (msg.role === 'system') {
    return <div className="chat-system">{msg.content}</div>;
  }
  const error = msg.role === 'agent' && msg.kind === 'error';
  const cls =
    msg.role === 'user'
      ? 'chat-bubble chat-bubble--user'
      : `chat-bubble chat-bubble--agent${error ? ' chat-bubble--error' : ''}`;

  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(msg.content);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      addToast({ type: 'error', message: t('chat:msg.copyFailed') });
    }
  };

  // The action bar lives OUTSIDE the bubble (below it), so user bubbles keep
  // their clean pill shape; rating expands in place from the bar.
  return (
    <div className="chat-entry">
      <div className={cls} role={error ? 'alert' : undefined}>
        <div className="chat-md">
          <ChatMarkdown content={msg.content} />
        </div>
      </div>
      <div className="chat-msg-actions">
        <button type="button" onClick={() => void onCopy()} aria-label={t('chat:msg.copy')}>
          {copied ? t('chat:msg.copied') : t('chat:msg.copy')}
        </button>
        <MessageForkButton msg={msg} />
        {msg.role === 'agent' && !error ? (
          <button type="button" aria-expanded={rateOpen} onClick={() => setRateOpen(!rateOpen)}>
            {t('chat:rate.open')}
          </button>
        ) : null}
      </div>
      {msg.role === 'agent' && !error && rateOpen ? (
        <RateBar subject={subject} onDone={() => setRateOpen(false)} />
      ) : null}
    </div>
  );
}

/** Fork: branch a new session from the conversation up to and including this
 *  message. keep_messages counts user/assistant entries in the persisted
 *  history, which maps 1:1 onto the visible non-system timeline. */
function MessageForkButton({ msg }: { msg: ChatMessage }) {
  const { t } = useTranslation('chat');
  const addToast = useUIStore((s) => s.addToast);
  const navigate = useNavigate();
  const messages = useChatStore((s) => s.messages);
  const [busy, setBusy] = useState(false);
  const index = messages.findIndex((m) => m.seq === msg.seq);
  const keep = messages
    .slice(0, index + 1)
    .filter((m) => m.role === 'user' || m.role === 'agent').length;

  const onFork = async () => {
    if (busy) return;
    setBusy(true);
    try {
      const state = useChatStore.getState();
      const created = await forkSession(state.activeSessionId, '', keep);
      const newId = created.session_id;
      await setActiveSession(newId);
      const loaded = state.switchSession(newId);
      if (!loaded) await loadSessionTimeline(newId);
      await loadChatSessions();
      navigate(routes.chat);
      addToast({ type: 'success', message: t('chat:msg.forked') });
    } catch (err) {
      addToast({
        type: 'error',
        message: err instanceof ServiceError ? extractErrorMessage(err) : String(err),
      });
    } finally {
      setBusy(false);
    }
  };

  return (
    <button
      type="button"
      disabled={busy}
      onClick={() => void onFork()}
      aria-label={t('chat:msg.fork')}
    >
      {t('chat:msg.fork')}
    </button>
  );
}

/** Star rating + comment for the finished turn; the verdict lands in agent
 *  memory (rate_turn) and guides later execution. Not persisted per message:
 *  the submission itself is the memory, so a refresh resets the form. */
function RateBar({ subject, onDone }: { subject: string; onDone: () => void }) {
  const { t } = useTranslation('chat');
  const addToast = useUIStore((s) => s.addToast);
  const [score, setScore] = useState(0);
  const [comment, setComment] = useState('');
  const [busy, setBusy] = useState(false);
  const submit = async () => {
    if (busy || score === 0) return;
    setBusy(true);
    try {
      await rateTurn(score, comment.trim(), subject.slice(0, 60));
      onDone();
    } catch (err) {
      addToast({
        type: 'error',
        message: err instanceof ServiceError ? extractErrorMessage(err) : String(err),
      });
    } finally {
      setBusy(false);
    }
  };
  return (
    <div className="chat-rate">
      <span className="chat-rate__stars" role="radiogroup" aria-label={t('chat:rate.title')}>
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n}
            type="button"
            role="radio"
            aria-checked={score === n}
            aria-label={t('chat:rate.star', { n })}
            className={n <= score ? 'is-on' : ''}
            onClick={() => setScore(n)}
          >
            ★
          </button>
        ))}
      </span>
      <input
        className="chat-rate__comment"
        value={comment}
        placeholder={t('chat:rate.placeholder')}
        maxLength={200}
        onChange={(e) => setComment(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') void submit();
        }}
      />
      <button type="button" disabled={score === 0 || busy} onClick={() => void submit()}>
        {t('chat:rate.submit')}
      </button>
    </div>
  );
}

/** Note artifact card: shows a summary row by default; clicking expands an inline
 *  Markdown preview in place, clicking again collapses it. The link to the notes
 *  page stays at the end of the row. Office artifacts are not supported: the
 *  aggregation backend has no office preview surface. */
function NoteArtifactCard({ artifact }: { artifact: NoteArtifact }) {
  const { t } = useTranslation('chat');
  const [open, setOpen] = useState(false);
  const [content, setContent] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const toggle = async () => {
    if (open) {
      setOpen(false);
      return;
    }
    setOpen(true);
    // Fetch the full body once: re-expanding does not refetch, and failed results
    // are remembered too (avoids repeatedly hitting a deleted note)
    if (content !== null || error !== null || loading) return;
    setLoading(true);
    try {
      const row = await getNote(artifact.noteId);
      setContent(String(row.content ?? ''));
    } catch (err) {
      // NOT_FOUND = the note was deleted or purged; show a readable explanation instead of a bare uuid error
      const code = err instanceof ServiceError ? err.code : '';
      setError(
        code.endsWith('NOT_FOUND')
          ? t('chat:noteArtifact.notFound')
          : err instanceof Error
            ? err.message
            : t('chat:noteArtifact.loadFailed')
      );
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="note-artifact">
      <button
        type="button"
        className="note-artifact__main"
        aria-expanded={open}
        onClick={() => void toggle()}
      >
        <span className="note-artifact__icon" aria-hidden>
          ▤
        </span>
        <span className="note-artifact__title">
          {t('chat:noteArtifact.created', { title: artifact.title })}
        </span>
        <span className="small muted">
          {open ? t('chat:noteArtifact.collapse') : t('chat:noteArtifact.expand')}
        </span>
      </button>
      <Link to={routes.note(artifact.noteId)} className="note-artifact__open small">
        {t('chat:noteArtifact.openPage')}
      </Link>
      {open ? (
        <div className="note-artifact__preview chat-md">
          {loading ? <span className="small muted">{t('chat:noteArtifact.loading')}</span> : null}
          {!loading && error ? <span className="small">⚠ {error}</span> : null}
          {!loading && !error && content !== null ? (
            content ? (
              <ChatMarkdown content={content} />
            ) : (
              <span className="small muted">{t('chat:noteArtifact.empty')}</span>
            )
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
