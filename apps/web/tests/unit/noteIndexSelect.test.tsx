/**
 * @file noteIndexSelect
 * @description Unit tests for the notes home bulk selection: scope wording,
 * entering bulk mode without checkboxes until a note is picked, selection
 * info/actions visibility, and clearing the selection.
 */

import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeAll, describe, expect, it, vi } from 'vitest';
import { initI18n } from '@/i18n';
import type { Note } from '@/api/types';
import { NoteIndex } from '@/pages/notes/NoteIndex';

// NoteIndex copy comes from the notes namespace; init once so t() resolves zh-CN
beforeAll(() => {
  initI18n();
});

function sample(partial: Partial<Note> = {}): Note {
  return {
    id: 'n1',
    title: '标题甲',
    content: '摘要正文',
    source_id: '',
    tags: [],
    created_ts: 1_700_000_000,
    updated_ts: 1_700_000_000,
    pinned: false,
    archived: false,
    ...partial,
  };
}

function renderIndex(notes: Note[] = [sample(), sample({ id: 'n2', title: '标题乙' })]) {
  return render(
    <NoteIndex
      notes={notes}
      layout="list"
      listState="active"
      onLayoutChange={vi.fn()}
      onListStateChange={vi.fn()}
      query=""
      onQuery={vi.fn()}
      sort="updated"
      onSort={vi.fn()}
      filter="all"
      onFilter={vi.fn()}
      sourceId=""
      onSourceId={vi.fn()}
      density="comfortable"
      onDensity={vi.fn()}
      projectOptions={[]}
      projectNames={new Map()}
      onOpen={vi.fn()}
      onNew={vi.fn()}
      onTrash={vi.fn()}
      onAssist={vi.fn()}
      onPin={vi.fn()}
      onArchive={vi.fn()}
      onExport={vi.fn()}
      onDelete={vi.fn()}
      empty={notes.length === 0}
    />
  );
}

describe('notes home bulk selection', () => {
  it('home scope uses "current", not "in use"', () => {
    renderIndex();
    expect(screen.getByTestId('notes-list-state-active')).toHaveTextContent('当前');
    expect(screen.queryByText('在用')).toBeNull();
  });

  it('no checkboxes appear after entering bulk mode and no selection info before anything is picked', () => {
    renderIndex();
    expect(screen.queryByRole('checkbox')).toBeNull();
    fireEvent.click(screen.getByTestId('notes-select-btn'));
    expect(screen.queryByRole('checkbox')).toBeNull();
    expect(screen.queryByTestId('notes-bulk-bar')).toBeNull();
    expect(screen.getByTestId('notes-select-btn')).toHaveAccessibleName('完成');
    expect(screen.getByTestId('notes-bulk-select-all')).toHaveAccessibleName('全选');
  });

  it('picking any note immediately shows the selection info and actions', () => {
    renderIndex();
    fireEvent.click(screen.getByTestId('notes-select-btn'));
    fireEvent.click(screen.getAllByTestId('note-item')[0]);
    expect(screen.getAllByTestId('note-item')[0]).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByTestId('notes-bulk-bar')).toHaveTextContent('已选 1 篇');
    expect(screen.getByTestId('notes-bulk-archive')).toBeTruthy();
    expect(screen.getByTestId('notes-bulk-export')).toBeTruthy();
    expect(screen.getByTestId('notes-bulk-delete')).toBeTruthy();
  });

  it('after clearing the selection the info bar exits before unmounting and bulk mode is kept', () => {
    vi.useFakeTimers();
    try {
      renderIndex();
      fireEvent.click(screen.getByTestId('notes-select-btn'));
      fireEvent.click(screen.getAllByTestId('note-item')[0]);
      fireEvent.click(screen.getByTestId('notes-bulk-clear'));
      expect(screen.getByTestId('notes-bulk-bar').className).toMatch(/is-exit/);
      act(() => {
        vi.advanceTimersByTime(420);
      });
      expect(screen.queryByTestId('notes-bulk-bar')).toBeNull();
      expect(screen.queryByRole('checkbox')).toBeNull();
      expect(screen.getByTestId('notes-select-btn')).toHaveAccessibleName('完成');
    } finally {
      vi.useRealTimers();
    }
  });
});
