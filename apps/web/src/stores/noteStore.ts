/**
 * @file noteStore.ts
 * @description Note body editing state (editing target, editor content/title, search,
 * selection).
 *
 * Interface preferences (font size / view layout) belong to notesUiStore —
 * keep them out of here.
 *
 * Responsibilities:
 * - Hold the editing target plus editor content/title; content accepts
 *   functional updates so batch pastes never write stale closure values
 * - Keep the list search query and the currently selected note id
 *
 * This module must not depend on UI-layer components.
 */
import { create } from 'zustand';

/** Note body editing state. Interface preferences (font size / view) live in notesUiStore — do not mix them in here. */

interface NoteState {
  editingNoteId: string | null;
  editorContent: string;
  editorTitle: string;
  searchQuery: string;
  selectedNoteId: string | null;
  startEditing: (noteId: string, title: string, content: string) => void;
  stopEditing: () => void;
  /** Supports functional updates: loops pasting multiple images avoid overwriting with stale render-closure values */
  setEditorContent: (content: string | ((prev: string) => string)) => void;
  setEditorTitle: (title: string) => void;
  setSearchQuery: (query: string) => void;
  setSelectedNoteId: (id: string | null) => void;
}

export const useNoteStore = create<NoteState>((set) => ({
  editingNoteId: null,
  editorContent: '',
  editorTitle: '',
  searchQuery: '',
  selectedNoteId: null,

  startEditing: (noteId, title, content) =>
    set({
      editingNoteId: noteId,
      editorTitle: title,
      editorContent: content,
      selectedNoteId: noteId,
    }),

  stopEditing: () =>
    set({
      editingNoteId: null,
      editorContent: '',
      editorTitle: '',
      selectedNoteId: null,
    }),

  setEditorContent: (content) =>
    set((s) => ({
      editorContent: typeof content === 'function' ? content(s.editorContent) : content,
    })),
  setEditorTitle: (title) => set({ editorTitle: title }),
  setSearchQuery: (query) => set({ searchQuery: query }),
  setSelectedNoteId: (id) => set({ selectedNoteId: id }),
}));
