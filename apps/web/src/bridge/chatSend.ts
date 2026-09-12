/**
 * @file chatSend.ts
 * @description Cross-domain chat contract: enqueue a chat message via POST /api/chat/messages.
 *
 * Shared by the floating chat and note explanation so there is a single fetch
 * path. The chat timeline and floating-window state belong to the chat domain;
 * non-chat pages may only touch them through the exported functions here.
 *
 * Responsibilities:
 * - Fetch chat history and enqueue chat messages over /api/chat/messages
 * - Apply the quota guard before user turns (block at full quota, warn at
 *   the threshold, then append locally and open the floating window)
 * - Expose the cross-domain timeline actions: system notes and interruption
 *   marking
 *
 * This module must not depend on UI-layer components.
 */

import { type ChatEvent, useChatStore } from '@/stores/chatStore';
import { useUIStore } from '@/stores/uiStore';
import { useFloatingStore } from '@/stores/floatingStore';
import { fetchQuotaGuard, quotaWarnMessage } from '@/bridge/quotaGuard';
import { cancelRun, listSessions } from '@/api/agent';
import { ServiceError } from '@/bridge/client';
import { extractErrorMessage } from '@/utils/errors';
import { i18n } from '@/i18n';

/** Chat history page: one window of the timeline plus whether older pages exist
 *  (has_more comes from the gateway's over-page probe). */
export interface ChatHistoryPage {
  messages: ChatEvent[];
  hasMore: boolean;
}

async function fetchHistoryPage(url: string): Promise<ChatHistoryPage> {
  const resp = await fetch(url, { credentials: 'include' });
  if (!resp.ok) {
    // History fetch failures must throw explicitly: silently returning [] would
    // make users believe they have no history
    throw new ServiceError(
      'UNKNOWN',
      i18n.t('chat:send.historyFailed', { status: resp.status }),
      '',
      '',
      resp.status
    );
  }
  const body = (await resp.json().catch(() => null)) as {
    messages?: ChatEvent[];
    has_more?: boolean;
  } | null;
  return { messages: body?.messages ?? [], hasMore: Boolean(body?.has_more) };
}

/** Session filter query suffix: empty session = unfiltered (legacy global view). */
function sessionQuery(session?: string): string {
  return session ? `&session=${encodeURIComponent(session)}` : '';
}

/** Newest history page (initial load): user.message + agent.message in one
 *  timeline, optionally narrowed to one chat session. */
export function fetchChatHistory(limit = 200, session?: string): Promise<ChatHistoryPage> {
  return fetchHistoryPage(`/api/chat/messages?limit=${limit}${sessionQuery(session)}`);
}

/** Older history page for backward paging: the window immediately before
 *  beforeSeq, ascending. */
export function fetchChatHistoryBefore(
  beforeSeq: number,
  limit = 200,
  session?: string
): Promise<ChatHistoryPage> {
  return fetchHistoryPage(
    `/api/chat/messages?before_seq=${beforeSeq}&limit=${limit}${sessionQuery(session)}`
  );
}

/** Newest trajectory window (initial load): agent.step rows for rebuilding
 *  per-turn trails; failures are silent (live steps still arrive over SSE).
 *  Newest-window only by design (matches the gateway contract): sessions
 *  beyond the window regroup from the live stream. */
export function fetchTrajectory(limit = 500, session?: string): Promise<ChatEvent[]> {
  return fetch(`/api/chat/trajectory?limit=${limit}${sessionQuery(session)}`, {
    credentials: 'include',
  })
    .then((resp) => {
      if (!resp.ok) throw new Error(String(resp.status));
      return resp.json().catch(() => null) as Promise<{ steps?: ChatEvent[] } | null>;
    })
    .then((body) => body?.steps ?? [])
    .catch(() => []);
}

export async function postChatMessage(content: string, session?: string): Promise<number> {
  const text = content.trim();
  if (!text) throw new Error(i18n.t('chat:send.empty'));
  const resp = await fetch('/api/chat/messages', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content: text, session: session ?? '' }),
  });
  const body = (await resp.json().catch(() => null)) as {
    seq?: number;
    error?: { code?: string; message?: string; hint?: string };
  } | null;
  // typeof check (not truthiness): seq=0 is a valid first message
  if (resp.ok && typeof body?.seq === 'number') return body.seq;
  // Prefer the backend error envelope's message over an uninformative status code
  const err = body?.error;
  throw new ServiceError(
    err?.code ?? 'UNKNOWN',
    err?.message ?? i18n.t('chat:send.failed', { status: resp.status }),
    err?.hint ?? '',
    '',
    resp.status
  );
}

/** Push a user message onto the main timeline from any page and open the floating
 *  chat (the floating window does not render while already on /chat). Requests pass
 *  through the same quota guard first: at full quota it throws (callers already have
 *  catch + error toast); at >= 80% it warns and still sends. Targets the active
 *  chat session. */
export async function sendUserTurn(content: string): Promise<void> {
  const guard = await fetchQuotaGuard();
  if (guard.action === 'block') throw new Error(guard.reason);
  if (guard.action === 'warn') {
    useUIStore.getState().addToast({ type: 'warning', message: quotaWarnMessage(guard.ratio) });
  }
  const session = useChatStore.getState().activeSessionId || undefined;
  const seq = await postChatMessage(content, session);
  useChatStore.getState().appendLocal({ seq, role: 'user', content: content.trim() });
  useFloatingStore.getState().setOpen(true);
}

/** Load the session list into the store (capability path). Failures keep the
 *  legacy global view: empty active id, unfiltered history — the chat never
 *  breaks because the session capability is unavailable. */
export async function loadChatSessions(): Promise<void> {
  try {
    const { sessions, active } = await listSessions();
    useChatStore.getState().setSessions(sessions, active);
  } catch {
    // legacy global view stays
  }
}

/** Backfill the OPEN lane (history + trajectory) for a session; call after
 *  switchSession returned false (lane not loaded yet). Applies only while the
 *  session is still the active one — a mid-fetch switch would otherwise smear
 *  one session's rows across another's timeline. Failures leave a system
 *  notice instead of a silently empty timeline. */
export async function loadSessionTimeline(sessionId: string): Promise<void> {
  const stillActive = () =>
    (useChatStore.getState().activeSessionId || undefined) === (sessionId || undefined);
  try {
    const page = await fetchChatHistory(200, sessionId || undefined);
    if (!stillActive()) return;
    useChatStore.getState().applyHistory(page.messages, page.hasMore);
  } catch {
    if (stillActive()) {
      useChatStore.getState().addSystem(i18n.t('chat:history.failedNotice'));
    }
    return;
  }
  if (!stillActive() || useChatStore.getState().messages.length === 0) return;
  const steps = await fetchTrajectory(500, sessionId || undefined);
  if (steps.length && stillActive()) useChatStore.getState().applyTrajectory(steps);
}

/** Interrupt a running agent instance over the capability bridge; 'chat' (the
 *  main conversation) also clears the thinking state so the composer's stop
 *  button and the side panel's agent list share one semantics. NOT_FOUND means
 *  the target was not running (typically stale thinking state). */
export async function interruptInstance(idOrName: string): Promise<void> {
  const stopChat = idOrName === 'chat';
  try {
    await cancelRun(idOrName);
  } catch (err) {
    const notFound = err instanceof ServiceError && err.code.includes('NOT_FOUND');
    if (stopChat) useChatStore.getState().clearThinking();
    useChatStore
      .getState()
      .addSystem(
        notFound
          ? i18n.t('chat:arbiter.notRunning')
          : i18n.t('chat:arbiter.stopFailed', { message: extractErrorMessage(err) })
      );
    return;
  }
  if (stopChat) useChatStore.getState().clearThinking();
  useChatStore
    .getState()
    .addSystem(
      stopChat
        ? i18n.t('chat:arbiter.stopped')
        : i18n.t('chat:arbiter.stopSent', { target: idOrName })
    );
}

// ---- Cross-domain chat contract -------------------------------------
// The chat timeline and floating-window toggle belong to chat-domain / shell
// state; non-chat pages only touch them via the functions below and never
// reach into the stores directly (enforced by ESLint no-restricted-imports).

/** Clear thinking after hard-stopping the conversation's main instance; optionally append a system bubble. Same semantics as interruptInstance's chat branch. */
export function markChatInterrupted(systemMessage?: string): void {
  useChatStore.getState().clearThinking();
  if (systemMessage) useChatStore.getState().addSystem(systemMessage);
}

/** Open the floating chat at the bottom-right. */
export function openFloatingChat(): void {
  useFloatingStore.getState().setOpen(true);
}

/** Append a system bubble to the chat timeline (error notices etc.; addSystem does not toggle the thinking indicator). */
export function chatSystemNote(content: string): void {
  useChatStore.getState().addSystem(content);
}
