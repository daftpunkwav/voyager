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
 * - Render inline turn traces (closed trails + live trace), system notices,
 *   task progress cards and the streaming indicator
 * - Load older history on scroll-to-top (backward paging), keeping the
 *   viewport anchored while rows are prepended
 * - Expand note artifact cards inline with on-demand note fetches
 */

import { useCallback, useEffect, useLayoutEffect, useRef, useState, Fragment } from 'react';
import { flushSync } from 'react-dom';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  type ChatMessage,
  type NoteArtifact,
  useChatStore,
} from '@/stores/chatStore';
import { fetchChatHistoryBefore } from '@/bridge/chatSend';
import { ServiceError } from '@/bridge/client';
import { getNote } from '@/api/notes';
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
  return out;
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
      {mergeTimeline(messages, artifacts).map((item) => {
        if (item.kind === 'artifact') {
          return <NoteArtifactCard key={`a${item.seq}`} artifact={item.artifact} />;
        }
        const m = item.msg;
        const trail = m.role === 'agent' ? trailBySeq.get(m.seq) : undefined;
        return (
          <Fragment key={`${m.seq ?? `local-${m.ts ?? item.seq}`}-${m.role}`}>
            {trail ? <ClosedTurnTrace steps={trail.steps} /> : null}
            <Bubble msg={m} />
          </Fragment>
        );
      })}
      <LiveTurnTrace />
      {showInterrupted && tailTrail ? <ClosedTurnTrace steps={tailTrail.steps} /> : null}
      {streaming?.text ? (
        // Streaming typing paragraph: same agent-text styling with a caret
        // indicating generation in progress; the final content arrives via
        // agent.message, this slot is transient display only
        <div className="chat-bubble chat-bubble--agent">
          <div className="chat-md">
            <ChatMarkdown content={streaming.text} />
            <span className="chat-caret" aria-hidden>
              ▍
            </span>
          </div>
        </div>
      ) : null}
      {thinking && !streaming?.text && steps.length === 0 ? (
        <div
          className="chat-bubble chat-bubble--agent chat-typing"
          aria-label={t('chat:typing.aria')}
        >
          <span />
          <span />
          <span />
        </div>
      ) : null}
      <div ref={bottomRef} />
    </div>
  );
}

function Bubble({ msg }: { msg: ChatMessage }) {
  if (msg.role === 'system') {
    return <div className="chat-system">{msg.content}</div>;
  }
  const cls =
    msg.role === 'user' ? 'chat-bubble chat-bubble--user' : 'chat-bubble chat-bubble--agent';
  return (
    <div className={cls}>
      <div className="chat-md">
        <ChatMarkdown content={msg.content} />
      </div>
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

/** Task progress card area (rendered in the side panel, with completed/failed final states). */
export function TaskCards() {
  const { t } = useTranslation('chat');
  const cards = useChatStore((s) => s.cards);
  const order = useChatStore((s) => s.cardOrder);
  const visible = order.map((k) => cards[k]).filter((c): c is NonNullable<typeof c> => Boolean(c));
  if (visible.length === 0) return null;
  return (
    <div className="chat-cards">
      {visible.map((c) => {
        const cls = `chat-card chat-card--${c.status}`;
        const body = (
          <>
            <div className="chat-card__head">
              {/* Full id visible on hover while label is occupied by project/kind */}
              <span className="chat-card__label" title={c.key}>
                {c.label}
              </span>
              <span className="chat-card__stage small muted">
                {c.status === 'failed'
                  ? t('chat:task.failedStage', {
                      error: c.error ?? t('chat:task.errorNotProvided'),
                    })
                  : c.stage}
              </span>
            </div>
            <div className="chat-card__bar">
              <div
                className="chat-card__fill"
                style={{ width: `${Math.round(c.progress * 100)}%` }}
              />
            </div>
          </>
        );
        // Cards with a resource detail page are fully clickable; graph job_ids have no
        // detail page, so they stay display-only
        return c.link ? (
          <Link key={c.key} to={c.link} className={`${cls} chat-card--link`}>
            {body}
          </Link>
        ) : (
          <div key={c.key} className={cls}>
            {body}
          </div>
        );
      })}
    </div>
  );
}
