/**
 * @file feed.ts
 * @description Shared types and summarization for the activity feed.
 *
 * FeedEvent / summarize power the activity page's agent-operations log: the
 * gateway's agent scope excludes conversation traffic and the user's own
 * actions, so the templates here describe only changes to the system (notes,
 * sources, files, settings, sessions). Summary copy resolves through the
 * chat namespace at call time.
 *
 * Responsibilities:
 * - Define the FeedEvent shape shared by feed consumers
 * - Summarize agent-operation events into localized one-line copy with a
 *   tone tag
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

/** Build a summary from per-type templates for the agent-operations feed.
 *  The gateway's agent scope already excludes conversation traffic and the
 *  user's own actions, so only operation templates live here; unrecognized
 *  types (an open set) render as muted raw text instead of throwing. */
export function summarize(ev: FeedEvent): RowSummary {
  const p = ev.payload;
  switch (ev.type) {
    case EventType.NOTE_CREATED:
      return {
        text: i18n.t('chat:feed.noteCreated', { title: clip(p.title, 40) }),
        tone: 'normal',
      };
    case EventType.NOTE_EDITED:
      return {
        text: i18n.t('chat:feed.noteEdited', { title: clip(p.title ?? p.note_id, 40) }),
        tone: 'normal',
      };
    case EventType.NOTE_DELETED:
      return {
        text: i18n.t('chat:feed.noteDeleted', { title: clip(p.title, 40) }),
        tone: 'muted',
      };
    case EventType.NOTE_RESTORED:
      return {
        text: i18n.t('chat:feed.noteRestored', { title: clip(p.title, 40) }),
        tone: 'normal',
      };
    case EventType.NOTE_PURGED:
      return {
        text: i18n.t('chat:feed.notePurged', { title: clip(p.title, 40) }),
        tone: 'muted',
      };
    case EventType.SESSION_DELETED:
      return {
        text: i18n.t('chat:feed.sessionDeleted', { title: clip(p.title, 40) }),
        tone: 'muted',
      };
    case EventType.SOURCE_ADDED:
      return {
        text: i18n.t('chat:feed.sourceAdded', { name: clip(p.name ?? p.title ?? p.source_id, 40) }),
        tone: 'normal',
      };
    case EventType.SOURCE_READY:
      return {
        text: i18n.t('chat:feed.sourceReady', { name: clip(p.name ?? p.title ?? p.source_id, 40) }),
        tone: 'normal',
      };
    case EventType.SOURCE_REMOVED:
      return {
        text: i18n.t('chat:feed.sourceRemoved', { name: clip(p.title ?? p.source_id, 40) }),
        tone: 'muted',
      };
    case EventType.AGENT_STEP: {
      // File-write tool calls are the "changed the system" slice of the step
      // stream (the gateway's agent scope pre-filters to these); read/search
      // steps that slip through with an explicit types filter degrade to the
      // tool name.
      if (p.kind === 'tool') {
        const tool = String(p.name ?? '');
        if (tool === 'write' || tool === 'edit') {
          const detail = (p.detail ?? {}) as Record<string, unknown>;
          const args = (detail.args ?? {}) as Record<string, unknown>;
          const path = clip(String(args.path ?? ''), 44);
          return {
            text: i18n.t(tool === 'write' ? 'chat:feed.fileWrite' : 'chat:feed.fileEdit', { path }),
            tone: 'normal',
          };
        }
        return { text: tool, tone: 'muted' };
      }
      return { text: ev.type, tone: 'muted' };
    }
    case EventType.SETTINGS_CHANGED:
      return {
        text: i18n.t('chat:feed.settingsChanged', { key: clip(p.key, 40) }),
        tone: 'normal',
      };
    default:
      return { text: ev.type, tone: 'muted' };
  }
}
