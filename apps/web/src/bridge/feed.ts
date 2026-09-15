/**
 * @file feed.ts
 * @description Shared types and summarization for the activity feed.
 *
 * FeedEvent / summarize are consumed by both the activity page and the
 * overview activity card; they live in the bridge layer so pages never import
 * each other's private implementations. Summary copy resolves through the
 * chat namespace at call time (zh output matches the pre-i18n templates).
 *
 * Responsibilities:
 * - Define the FeedEvent shape shared by feed consumers
 * - Summarize domain events into localized one-line copy with a tone tag
 *   (user/agent/note/source/task/settings/health/agent-observe families)
 * - Render unrecognized event types as muted raw text instead of throwing
 *
 * This module must not depend on UI-layer components.
 */

import { i18n } from '@/i18n';
import { EventType } from '@/bridge/events';

export interface FeedEvent {
  seq: number;
  id: string;
  type: string;
  actor: { kind: string; id: string };
  payload: Record<string, unknown>;
  ts: number;
  trace_id: string;
}

export type RowTone = 'normal' | 'error' | 'muted';

export interface RowSummary {
  text: string;
  tone: RowTone;
}

function clip(text: unknown, max = 60): string {
  const s = String(text ?? '');
  return s.length > max ? `${s.slice(0, max)}…` : s;
}

function actorName(actor: FeedEvent['actor']): string {
  if (actor.kind === 'user') return i18n.t('chat:feed.actorUser');
  if (actor.kind === 'agent') return actor.id || 'agent';
  return actor.id || 'system';
}

/** Build a summary from per-type templates; unrecognized types (an open set) render as muted raw text instead of throwing. */
export function summarize(ev: FeedEvent): RowSummary {
  const who = actorName(ev.actor);
  const p = ev.payload;
  switch (ev.type) {
    case EventType.USER_MESSAGE:
      return {
        text: i18n.t('chat:feed.userMessage', { who, content: clip(p.content) }),
        tone: 'normal',
      };
    case EventType.AGENT_MESSAGE: {
      // Proactive messages carry their trigger source so the activity page also shows "why you were contacted"
      if (p.proactive) {
        const why = String(p.reason ?? '').trim();
        return {
          text: i18n.t('chat:feed.agentProactive', {
            who,
            why: why ? `(${why})` : '',
            content: clip(p.content),
          }),
          tone: 'normal',
        };
      }
      return {
        text: i18n.t('chat:feed.agentReply', { who, content: clip(p.content) }),
        tone: 'normal',
      };
    }
    case EventType.USER_ONLINE:
      return { text: i18n.t('chat:feed.userOnline', { who }), tone: 'muted' };
    case EventType.USER_ACTIVITY:
      return {
        text: i18n.t('chat:feed.userActivity', {
          who,
          kind: String(p.kind ?? ''),
          page: clip(p.page, 30),
        }),
        tone: 'muted',
      };
    case EventType.NOTE_CREATED:
      return {
        text: i18n.t('chat:feed.noteCreated', { who, title: clip(p.title, 40) }),
        tone: 'normal',
      };
    case EventType.NOTE_EDITED:
      return {
        text: i18n.t('chat:feed.noteEdited', { who, noteId: clip(p.note_id, 12) }),
        tone: 'normal',
      };
    case EventType.NOTE_DELETED:
      return {
        text: i18n.t('chat:feed.noteDeleted', { who, title: clip(p.title, 40) }),
        tone: 'muted',
      };
    case EventType.SOURCE_ADDED:
      return {
        text: i18n.t('chat:feed.sourceAdded', { who, name: clip(p.name ?? p.source_id, 40) }),
        tone: 'normal',
      };
    case EventType.SOURCE_READY:
      return {
        text: i18n.t('chat:feed.sourceReady', { who, name: clip(p.name ?? p.source_id, 40) }),
        tone: 'normal',
      };
    case EventType.SOURCE_REMOVED:
      return {
        text: i18n.t('chat:feed.sourceRemoved', { who, sourceId: clip(p.source_id, 12) }),
        tone: 'muted',
      };
    case EventType.TASK_ENQUEUED:
      return {
        text: i18n.t('chat:feed.taskEnqueued', { who, target: clip(p.project ?? p.source_id, 30) }),
        tone: 'muted',
      };
    case EventType.TASK_PROGRESS: {
      const pct = Math.round(Number(p.progress ?? 0) * 100);
      return {
        text: i18n.t('chat:feed.taskProgress', { who, pct, stage: clip(p.stage, 20) }),
        tone: 'muted',
      };
    }
    case EventType.TASK_COMPLETED:
      return {
        text: i18n.t('chat:feed.taskCompleted', {
          who,
          target: clip(p.project ?? p.source_id, 30),
        }),
        tone: 'normal',
      };
    case EventType.TASK_FAILED:
      return {
        text: i18n.t('chat:feed.taskFailed', { who, error: clip(p.error, 60) }),
        tone: 'error',
      };
    case EventType.SETTINGS_CHANGED:
      return {
        text: i18n.t('chat:feed.settingsChanged', { who, key: clip(p.key, 40) }),
        tone: 'normal',
      };
    case EventType.SERVICE_HEALTH_CHANGED:
      return {
        text: i18n.t('chat:feed.serviceHealth', {
          service: clip(p.service, 20),
          status: String(p.status ?? ''),
        }),
        tone: p.status === 'up' ? 'muted' : 'error',
      };
    case EventType.GRAPH_ENGINE_FALLBACK:
      return {
        text: i18n.t('chat:feed.graphFallback', { reason: clip(p.reason, 50) }),
        tone: 'muted',
      };
    case EventType.AGENT_ASK:
      return { text: i18n.t('chat:feed.agentAsk', { who }), tone: 'normal' };
    case EventType.AGENT_OBSERVE: {
      // Agent observation notices (considerations such as resources becoming ready); acted = a task was dispatched automatically
      const acted = p.acted ? i18n.t('chat:feed.agentObserveActed') : '';
      return {
        text: i18n.t('chat:feed.agentObserve', { who, content: clip(p.content), acted }),
        tone: 'muted',
      };
    }
    case EventType.AGENT_NAVIGATE:
      return {
        text: i18n.t('chat:feed.agentNavigate', { who, path: clip(p.path ?? p.to, 20) }),
        tone: 'muted',
      };
    default:
      return { text: ev.type, tone: 'muted' };
  }
}
