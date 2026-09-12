/**
 * @file noteTrash
 * @description Unit tests for the notes trash panel restore flow: a restored
 * note stays in the trash list and the note detail does not open.
 */

import { fireEvent, render, screen } from '@testing-library/react';
import { beforeAll, vi } from 'vitest';
import { initI18n } from '@/i18n';
import { TrashPanel } from '@/pages/notes/NoteTrash';

// TrashPanel copy comes from the notes namespace; init once so t() resolves zh-CN
beforeAll(() => {
  initI18n();
});

const { restoreMutate } = vi.hoisted(() => ({
  restoreMutate: vi.fn((_id: string, opts?: { onSuccess?: () => void }) => {
    opts?.onSuccess?.();
  }),
}));

vi.mock('@/hooks/useNotes', () => ({
  useTrashNotes: () => ({
    data: [{ id: 'n1', title: '已删笔记', updated_ts: 1 }],
  }),
  useRestoreNote: () => ({ mutate: restoreMutate, isPending: false }),
  usePurgeNote: () => ({ mutate: vi.fn(), isPending: false }),
  useEmptyTrash: () => ({ mutate: vi.fn(), isPending: false }),
}));

describe('trash restore', () => {
  it('stays in the trash after restore and does not open the note detail', () => {
    const onClose = vi.fn();
    render(<TrashPanel open onClose={onClose} />);

    fireEvent.click(screen.getByRole('button', { name: '恢复' }));

    expect(restoreMutate).toHaveBeenCalledWith('n1', expect.any(Object));
    expect(onClose).not.toHaveBeenCalled();
    expect(screen.getByRole('dialog', { name: '回收站' })).toBeTruthy();
  });
});
