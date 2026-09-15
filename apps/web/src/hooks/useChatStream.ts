/**
 * @file useChatStream
 * @description Wires the chat stream for both the chat page and the persistent
 * floating window: load history, then subscribe to SSE.
 *
 * Resume-after-disconnect is handled by bridge/stream; history goes through
 * bridge/chatSend (single timeline; all backend chat access
 * is funneled through the bridge layer).
 *
 * Responsibilities:
 * - On mount: rebuild history, subscribe to the chat SSE
 *   patterns, and mark the store connected; mirrored on unmount
 * - Forward stream events into chatStore, intercepting agent.navigate
 *   (validated internal path) and policy notices (info toast, no timeline)
 * - Toast failed background resumes before their card lands in the store
 */

import { useEffect } from 'react';
import { fetchChatHistory, fetchTrajectory, loadChatSessions } from '@/bridge/chatSend';
import { subscribe } from '@/bridge/stream';
import { EventType } from '@/bridge/events';
import { safeInternalPath } from '@/utils/safeUrl';
import { type ChatEvent, useChatStore } from '@/stores/chatStore';
import { useUIStore } from '@/stores/uiStore';
import { i18n } from '@/i18n';

const STREAM_PATTERNS = [
  EventType.AGENT_MESSAGE,
  EventType.AGENT_ASK,
  EventType.AGENT_NAVIGATE,
  EventType.AGENT_STEP,
  EventType.AGENT_DELTA,
  EventType.AGENT_POLICY_NOTIFY,
  'task.*', // subscription glob, not a concrete type
  EventType.NOTE_CREATED,
  EventType.WORKSPACE_SWITCHED,
];

export function useChatStream(onNavigate: (path: string) => void) {
  useEffect(() => {
    // Session list first: the active session id scopes the history fetch.
    // Capability failures keep the legacy global view (no session filter).
    loadChatSessions()
      .then(() => {
        const sid = useChatStore.getState().activeSessionId || undefined;
        const stillActive = () => (useChatStore.getState().activeSessionId || undefined) === sid;
        // The message stream starts from now; history failures leave a trace
        // in the session so "no history" and "history failed to load" stay
        // distinguishable for the user
        return (
          fetchChatHistory(200, sid)
            .then((page) => {
              // Stale-apply guard: if the user switched sessions while the
              // fetch was in flight, this page belongs to the previous lane;
              // dropping it is safe (switch refetches an unloaded lane, and
              // the event log stays the source of truth)
              if (!stillActive()) return;
              useChatStore.getState().applyHistory(page.messages, page.hasMore);
            })
            .catch(() => {
              if (!stillActive()) return;
              useChatStore.getState().addSystem(i18n.t('chat:history.failedNotice'));
            })
            // Trajectory backfill runs after history settles: grouping needs the
            // messages in place, otherwise every step lands in the open turn.
            // Skipped when history failed (ungroupable steps are worse than none;
            // the live step stream still covers new turns). Failures stay silent.
            .finally(() => {
              if (!stillActive()) return;
              if (useChatStore.getState().messages.length === 0) return;
              fetchTrajectory(500, sid).then((steps) => {
                if (steps.length && stillActive()) {
                  useChatStore.getState().applyTrajectory(steps);
                }
              });
            })
        );
      })
      .catch(() => {
        useChatStore.getState().addSystem(i18n.t('chat:history.failedNotice'));
      });
    const off = subscribe(STREAM_PATTERNS, (ev) => {
      if (ev.type === EventType.AGENT_NAVIGATE) {
        const path = safeInternalPath(ev.payload.path);
        if (path) onNavigate(path);
        return;
      }
      if (ev.type === EventType.AGENT_POLICY_NOTIFY) {
        // L1 permission notice: surface as an info toast only, never into the chat timeline
        const msg = String(ev.payload?.message ?? '').trim();
        if (msg) useUIStore.getState().addToast({ type: 'info', message: msg });
        return;
      }
      if (ev.type === EventType.WORKSPACE_SWITCHED) {
        // Another tab switched the workspace: toast once, then let the store
        // bump drive workspace views to refetch (no timeline entry).
        const dir = String(ev.payload?.workspace ?? '').trim();
        useUIStore.getState().addToast({
          type: 'info',
          message: i18n.t('chat:workspace.switchedElsewhere', { dir }),
        });
      }
      if (ev.type === EventType.TASK_FAILED && ev.payload?.kind === 'resume') {
        // A failed background resume: its card lives in chatStore (job_id = run_id),
        // so also raise an immediate toast and collapse the floating window as a
        // fallback; other task.failed kinds (code_exec/sources/graph) still go
        // through cards only
        const error =
          String(ev.payload?.error ?? '').trim() || i18n.t('chat:task.errorNotProvided');
        useUIStore.getState().addToast({
          type: 'error',
          message: i18n.t('chat:task.resumeFailed', { error }),
        });
      }
      useChatStore.getState().dispatch(ev as ChatEvent);
    });
    useChatStore.getState().setConnected(true);

    return () => {
      off();
      useChatStore.getState().setConnected(false);
    };
  }, [onNavigate]);
}
