/**
 * @file notesUiBridge
 * @description Notes UI bridge: initial fetch plus settings.changed / notes.ui.changed events into the store, with navigation support.
 *
 * Mounted by App via AppShell (bridges) so an agent calling set_notes_view on
 * any page can change the notes UI or open a note. The app shell must not
 * import this module; removing the notes domain only requires dropping the
 * injection in App.
 *
 * Responsibilities:
 * - Fetch the notes view once at startup and seed the UI store (localStorage
 *   kept as fallback when the backend is down)
 * - Apply notes.ui.* setting changes and notes.ui.changed snapshots from
 *   agents, including open/index actions and the explain quote
 * - Invalidate notes queries on note.* lifecycle events
 */

import { useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { subscribe } from '@/bridge/stream';
import { EventType } from '@/bridge/events';
import { openFloatingChat } from '@/bridge/chatSend';
import { routes } from '@/utils/routes';
import {
  applyNotesSettingKey,
  applyNotesViewSnapshot,
  explainNotesQuote,
  fetchNotesView,
} from './notesView';

const NOTE_EVENTS = [
  EventType.NOTE_CREATED,
  EventType.NOTE_EDITED,
  EventType.NOTE_DELETED,
  EventType.NOTE_RESTORED,
  EventType.NOTE_PURGED,
] as const;

function useNotesUiBridge() {
  const navigate = useNavigate();
  const qc = useQueryClient();

  useEffect(() => {
    let alive = true;
    void fetchNotesView()
      .then((view) => {
        if (alive) applyNotesViewSnapshot(view);
      })
      .catch(() => {
        /* Backend not running: keep the localStorage seed and do not break the shell */
      });

    const offUi = subscribe([EventType.NOTES_UI_CHANGED, EventType.SETTINGS_CHANGED], (event) => {
      if (event.type === EventType.SETTINGS_CHANGED) {
        const key = event.payload.key;
        if (typeof key === 'string' && key.startsWith('notes.ui.')) {
          applyNotesSettingKey(key, event.payload.value);
        }
        return;
      }
      applyNotesViewSnapshot(event.payload);
      const quote = typeof event.payload.quote === 'string' ? event.payload.quote : '';
      if (quote.trim()) {
        explainNotesQuote(quote);
      } else if (event.payload.assist === true) {
        openFloatingChat();
      }
      const action = event.payload.action;
      const noteId = event.payload.note_id;
      if (action === 'index') {
        navigate(routes.notes);
        return;
      }
      if (
        action === 'open' &&
        typeof noteId === 'string' &&
        noteId &&
        noteId.length <= 200 &&
        !noteId.includes('/') &&
        !noteId.includes('\\')
      ) {
        navigate(noteId === 'new' ? routes.note('new') : routes.note(noteId));
      }
    });

    const offNotes = subscribe([...NOTE_EVENTS], (event) => {
      void qc.invalidateQueries({ queryKey: ['notes'] });
      if (event.type === EventType.NOTE_EDITED || event.type === EventType.NOTE_CREATED) {
        const nid = event.payload.note_id;
        if (typeof nid === 'string' && nid) {
          void qc.invalidateQueries({ queryKey: ['note', nid] });
        }
      }
    });

    return () => {
      alive = false;
      offUi();
      offNotes();
    };
  }, [navigate, qc]);
}

/** Null-rendering host: side effects hang on it; mounted by App through AppShell.bridges. */
export function NotesUiBridge() {
  useNotesUiBridge();
  return null;
}
