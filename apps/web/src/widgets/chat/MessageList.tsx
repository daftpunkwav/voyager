/**
 * @file MessageList
 * @description Renders the chat message stream: user/agent bubbles (Markdown +
 * highlight), system notices, task progress cards and the thinking state.
 *
 * Shared by the chat page and the persistent floating window; lives in the
 * widgets layer so page-private components are never depended on in reverse.
 *
 * Responsibilities:
 * - Render user / agent bubbles with sanitized Markdown and highlighting
 * - Render system notices, task progress cards and the streaming indicator
 * - Load older history on scroll-to-top (backward paging), keeping the
 *   viewport anchored while rows are prepended
 * - Expand note artifact cards inline with on-demand note fetches
 */

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { flushSync } from 'react-dom';
import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize';
import type { Options as SanitizeOptions } from 'rehype-sanitize';
import { type ChatMessage, type NoteArtifact, useChatStore } from '@/stores/chatStore';
import { fetchChatHistoryBefore } from '@/bridge/chatSend';
import { ServiceError } from '@/bridge/client';
import { getNote } from '@/api/notes';
import { routes } from '@/utils/routes';
import { safeHttpUrl, safeInternalPath } from '@/utils/safeUrl';
import { i18n } from '@/i18n';

/** class names highlight.js may inject; same allowlist line as MarkdownRenderer (defense in depth). */
const sanitizeSchema: SanitizeOptions = {
  ...defaultSchema,
  attributes: {
    ...defaultSchema.attributes,
    code: [...(defaultSchema.attributes?.code ?? []), ['className']],
    span: [...(defaultSchema.attributes?.span ?? []), ['className']],
    pre: [...(defaultSchema.attributes?.pre ?? []), ['className']],
  },
};

const mdComponents: Components = {
  a({ href, children }) {
    const internal = safeInternalPath(href);
    if (internal) return <a href={internal}>{children}</a>;
    const http = safeHttpUrl(href);
    if (http) {
      return (
        <a href={http} target="_blank" rel="noopener noreferrer">
          {children}
        </a>
      );
    }
    return <span>{children}</span>;
  },
};

/** Scroll-top distance that arms the backward-history load. */
const LOAD_TRIGGER_PX = 80;

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

export function MessageList() {
  const { t } = useTranslation('chat');
  const messages = useChatStore((s) => s.messages);
  const thinking = useChatStore((s) => s.thinking);
  const streaming = useChatStore((s) => s.streaming);
  const artifacts = useChatStore((s) => s.artifacts);
  const historyLoading = useChatStore((s) => s.historyLoading);
  const bottomRef = useRef<HTMLDivElement>(null);
  const streamRef = useRef<HTMLDivElement>(null);
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
    // viewport itself, so only tail growth (new messages) scrolls to bottom
    if (prev !== null && firstSeq !== null && firstSeq < prev) return;
    const reduce =
      typeof window !== 'undefined' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    bottomRef.current?.scrollIntoView({
      behavior: reduce ? 'auto' : 'smooth',
      block: 'end',
    });
  }, [firstSeq, messages.length, thinking, artifacts.length, streaming]);

  return (
    <div className="chat-stream" ref={streamRef}>
      {historyLoading ? (
        <div className="chat-history-loader small muted" role="status">
          {t('chat:history.loadingOlder')}
        </div>
      ) : null}
      {messages.map((m) => (
        <Bubble key={`${m.seq}-${m.role}`} msg={m} />
      ))}
      {artifacts.map((a) => (
        <NoteArtifactCard key={a.seq} artifact={a} />
      ))}
      {streaming?.text ? (
        // Streaming typing bubble: same agent-bubble styling with a caret indicating
        // generation in progress; the final content arrives via agent.message, this
        // slot is transient display only
        <div className="chat-bubble chat-bubble--agent">
          <div className="chat-md">
            <ChatMarkdown content={streaming.text} />
            <span className="chat-caret" aria-hidden>
              ▍
            </span>
          </div>
        </div>
      ) : null}
      {thinking ? (
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

/** In-chat Markdown rendering (GFM + highlight + allowlist sanitize); bubbles and artifact previews share the same pipeline. */
function ChatMarkdown({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[rehypeHighlight, [rehypeSanitize, sanitizeSchema]]}
      components={mdComponents}
    >
      {content}
    </ReactMarkdown>
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

/** Task progress card area (rendered above the composer, with completed/failed final states). */
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
