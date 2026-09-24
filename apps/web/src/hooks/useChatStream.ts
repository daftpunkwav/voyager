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
 *   (validated internal path); policy notices are dropped (the activity
 *   page is the operations log)
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
  // Team delivery cards: without this pattern the bridge drops live frames and
  // a card only appears after a refresh / history replay (the store's dispatch
  // and lane paths are seq-deduped, so a reconnect replay cannot double it).
  EventType.AGENT_DELIVERY,
  EventType.AGENT_POLICY_NOTIFY,
  EventType.SKILL_PROPOSED,
  'task.*', // subscription glob, not a concrete type
  EventType.NOTE_CREATED,
  EventType.WORKSPACE_SWITCHED,
];

export function useChatStream(onNavigate: (path: string) => void) {
  useEffect(() => {
    // StrictMode double-mounts this effect in dev: without the alive flag both
    // chains run to completion and failure paths add duplicate system bubbles
    let alive = true;
    // Session list first: the active session id scopes the history fetch.
    // Capability failures keep the legacy global view (no session filter).
    loadChatSessions()
      .then(() => {
        if (!alive) return undefined;
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
              if (!stillActive() || !alive) return;
              useChatStore.getState().applyHistory(page.messages, page.hasMore);
            })
            .catch(() => {
              if (!stillActive() || !alive) return;
              useChatStore.getState().addSystem(i18n.t('chat:history.failedNotice'));
            })
            // Trajectory backfill runs after history settles: grouping needs the
            // messages in place, otherwise every step lands in the open turn.
            // Skipped when history failed (ungroupable steps are worse than none;
            // the live step stream still covers new turns). Failures stay silent.
            .finally(() => {
              if (!stillActive() || !alive) return;
              if (useChatStore.getState().messages.length === 0) return;
              fetchTrajectory(500, sid).then((steps) => {
                if (steps.length && stillActive() && alive) {
                  useChatStore.getState().applyTrajectory(steps);
                }
              });
            })
        );
      })
      .catch(() => {
        if (!alive) return;
        useChatStore.getState().addSystem(i18n.t('chat:history.failedNotice'));
      });
    const off = subscribe(STREAM_PATTERNS, (ev) => {
      if (ev.type === EventType.AGENT_NAVIGATE) {
        const path = safeInternalPath(ev.payload.path);
        if (path) onNavigate(path);
        return;
      }
      if (ev.type === EventType.AGENT_POLICY_NOTIFY) {
        // L1 permission notices (one per write call, so they flood during
        // batch operations) are no longer surfaced here: the activity page is
        // the operations log, and the tool rows in the trail show the calls.
        return;
      }
      if (ev.type === EventType.SKILL_PROPOSED) {
        // Skill proposal: a non-blocking sidebar notification (toast + activity
        // feed), never the ask_user modal — agreeing happens in conversation
        const sequence = Array.isArray(ev.payload?.sequence) ? ev.payload.sequence : [];
        const flow = sequence.map((s) => String(s)).join(' → ');
        if (flow) {
          useUIStore.getState().addToast({
            type: 'info',
            message: i18n.t('chat:skill.proposed', {
              flow,
              count: Number(ev.payload?.count ?? 0),
            }),
          });
        }
        return;
      }
      if (ev.type === EventType.WORKSPACE_SWITCHED) {
        // Another tab switched the workspace: toast once, then let the store
        // bump drive workspace views to refetch (no timeline entry). The
        // broadcast reaches the initiating tab too; its own marker means the
        // "switched elsewhere" copy would be wrong, so skip the toast (the
        // revision bump below still refreshes the views).
        const marker = typeof ev.payload?.marker === 'string' ? ev.payload.marker : '';
        const mine = marker !== '' && marker === useChatStore.getState().workspaceSwitchMarker;
        if (mine) {
          useChatStore.setState({ workspaceSwitchMarker: null });
        } else {
          const dir = String(ev.payload?.workspace ?? '').trim();
          if (dir) {
            useUIStore.getState().addToast({
              type: 'info',
              message: i18n.t('chat:workspace.switchedElsewhere', { dir }),
            });
          }
        }
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
      alive = false;
      off();
      useChatStore.getState().setConnected(false);
    };
  }, [onNavigate]);
}
