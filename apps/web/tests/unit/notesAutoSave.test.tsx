/**
 * @file notesAutoSave
 * @description Behavior tests for the editor autosave slice, centered on the
 * in-flight-save race: keystrokes that land while an update request is still
 * pending must stay dirty (and re-arm the debounce) instead of being silently
 * dropped behind a "saved" indicator; a clean save still clears the flag.
 */

import { act, renderHook } from '@testing-library/react';
import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';
import { initI18n } from '@/i18n';
import { useUIStore } from '@/stores/uiStore';
import { useNoteStore } from '@/stores/noteStore';
import { useNotesAutoSave } from '@/pages/notes/notesAutoSave';

const mutateAsync = vi.hoisted(() => vi.fn());

vi.mock('@/hooks/useNotes', () => ({
  useUpdateNote: () => ({ mutateAsync, isPending: false }),
  useCreateNote: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

vi.mock('react-router-dom', () => ({
  useSearchParams: () => [new URLSearchParams(), vi.fn()],
}));

beforeEach(() => {
  initI18n();
  vi.useFakeTimers();
  mutateAsync.mockReset();
  mutateAsync.mockResolvedValue({});
  act(() => {
    useNoteStore.setState({
      editingNoteId: 'n1',
      editorTitle: 'T',
      editorContent: 'C1',
    });
    useUIStore.setState({ toasts: [] });
  });
});

afterEach(() => {
  vi.useRealTimers();
});

function renderAutosave() {
  return renderHook(() => useNotesAutoSave({ newProjectId: '' }));
}

async function flushIgnoringTimers(hook: ReturnType<typeof renderAutosave>) {
  let result!: boolean;
  await act(async () => {
    result = await hook.result.current.flush();
  });
  return result;
}

describe('notesAutoSave', () => {
  it('clears dirty and reports saved when the editor holds the persisted content', async () => {
    const hook = renderAutosave();
    // markDirty is internal; the store-driven effect and the flush gate both
    // key off this ref, so set it the way a keystroke would
    act(() => {
      hook.result.current.dirtyRef.current = true;
    });

    const ok = await flushIgnoringTimers(hook);

    expect(ok).toBe(true);
    expect(mutateAsync).toHaveBeenCalledWith({ id: 'n1', title: 'T', content: 'C1' });
    expect(hook.result.current.dirtyRef.current).toBe(false);
    expect(hook.result.current.saveState).toBe('saved');
  });

  it('keeps dirty and re-arms when keystrokes land during the in-flight save', async () => {
    const hook = renderAutosave();
    act(() => {
      hook.result.current.dirtyRef.current = true;
    });

    let resolveSave!: (v: unknown) => void;
    mutateAsync.mockImplementation(() => new Promise((resolve) => (resolveSave = resolve)));

    let pending!: Promise<boolean>;
    act(() => {
      pending = hook.result.current.flush();
    });

    // Keystrokes land while the first request is in flight
    act(() => {
      useNoteStore.setState({ editorContent: 'C1 plus new typing' });
    });

    await act(async () => {
      resolveSave({});
      await pending;
    });

    // The newer keystrokes must not be silently dropped behind "saved"
    expect(hook.result.current.dirtyRef.current).toBe(true);
    expect(hook.result.current.saveState).toBe('unsaved');

    // The debounce re-arms and persists the newer content
    mutateAsync.mockReset();
    mutateAsync.mockResolvedValue({});
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(mutateAsync).toHaveBeenCalledTimes(1);
    expect(mutateAsync).toHaveBeenCalledWith({
      id: 'n1',
      title: 'T',
      content: 'C1 plus new typing',
    });
  });
});
