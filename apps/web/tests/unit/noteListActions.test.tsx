/**
 * @file noteListActions
 * @description Unit tests for note list item actions: selection-mode
 * checkboxes vs opening notes, and menu actions (archive/export/move to
 * trash) without opening the note.
 */

import { fireEvent, render, screen } from '@testing-library/react';
import { useState } from 'react';
import { beforeAll, vi } from 'vitest';
import { initI18n } from '@/i18n';
import type { Note } from '@/api/types';
import { NoteList } from '@/pages/notes/NoteList';

// NoteList copy comes from the notes namespace; init once so t() resolves zh-CN
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

function Harness({
  variant,
  selecting = false,
  onSelect,
  onToggleSelect,
  onArchive,
  onExport,
  onDelete,
}: {
  variant: 'list' | 'card';
  selecting?: boolean;
  onSelect: (n: Note) => void;
  onToggleSelect: (id: string) => void;
  onArchive: (n: Note) => void;
  onExport: (n: Note) => void;
  onDelete: (n: Note) => void;
}) {
  const [menuId, setMenuId] = useState<string | null>(null);
  return (
    <NoteList
      notes={[sample()]}
      variant={variant}
      selectedIds={new Set()}
      menuId={menuId}
      selecting={selecting}
      onSelect={onSelect}
      onToggleSelect={onToggleSelect}
      onMenu={setMenuId}
      onArchive={onArchive}
      onExport={onExport}
      onDelete={onDelete}
      onPin={() => undefined}
    />
  );
}

describe('note list item actions', () => {
  it('renders no checkboxes when not in selection mode', () => {
    render(
      <Harness
        variant="card"
        onSelect={vi.fn()}
        onToggleSelect={vi.fn()}
        onArchive={vi.fn()}
        onExport={vi.fn()}
        onDelete={vi.fn()}
      />
    );
    expect(screen.queryByRole('checkbox')).toBeNull();
  });

  it('in selection mode clicking an item only selects it, does not open it', () => {
    const onSelect = vi.fn();
    const onToggleSelect = vi.fn();
    render(
      <Harness
        variant="list"
        selecting
        onSelect={onSelect}
        onToggleSelect={onToggleSelect}
        onArchive={vi.fn()}
        onExport={vi.fn()}
        onDelete={vi.fn()}
      />
    );
    expect(screen.queryByRole('checkbox')).toBeNull();
    fireEvent.click(screen.getByTestId('note-item'));
    expect(onToggleSelect).toHaveBeenCalledWith('n1');
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('in selection mode clicking a card only checks it, does not open it', () => {
    const onSelect = vi.fn();
    const onToggleSelect = vi.fn();
    render(
      <Harness
        variant="card"
        selecting
        onSelect={onSelect}
        onToggleSelect={onToggleSelect}
        onArchive={vi.fn()}
        onExport={vi.fn()}
        onDelete={vi.fn()}
      />
    );
    fireEvent.click(screen.getByTestId('note-item'));
    expect(onToggleSelect).toHaveBeenCalledWith('n1');
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('the list menu can archive and export without opening the note', () => {
    const onSelect = vi.fn();
    const onArchive = vi.fn();
    const onExport = vi.fn();
    render(
      <Harness
        variant="list"
        onSelect={onSelect}
        onToggleSelect={vi.fn()}
        onArchive={onArchive}
        onExport={onExport}
        onDelete={vi.fn()}
      />
    );
    fireEvent.click(screen.getByRole('button', { name: '笔记操作' }));
    fireEvent.click(screen.getByRole('menuitem', { name: '归档' }));
    expect(onArchive).toHaveBeenCalledTimes(1);
    expect(onSelect).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: '笔记操作' }));
    fireEvent.click(screen.getByRole('menuitem', { name: '导出 Markdown' }));
    expect(onExport).toHaveBeenCalledTimes(1);
    expect(onSelect).not.toHaveBeenCalled();
  });

  it('the card menu can move to trash without opening the note', () => {
    const onSelect = vi.fn();
    const onDelete = vi.fn();
    render(
      <Harness
        variant="card"
        onSelect={onSelect}
        onToggleSelect={vi.fn()}
        onArchive={vi.fn()}
        onExport={vi.fn()}
        onDelete={onDelete}
      />
    );
    fireEvent.click(screen.getByRole('button', { name: '笔记操作' }));
    fireEvent.click(screen.getByRole('menuitem', { name: '移入回收站' }));
    expect(onDelete).toHaveBeenCalledTimes(1);
    expect(onSelect).not.toHaveBeenCalled();
  });
});
