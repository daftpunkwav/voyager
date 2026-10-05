/**
 * @file updateProgressSerialization
 * @description Locks the per-project write queue in useUpdateProgress: rapid
 * progress changes must reach the API in key order on the same project, while
 * different projects stay independent.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import type { ReactNode } from 'react';
import { updateProgress } from '@/api/projects';
import { useUpdateProgress } from '@/hooks/useProjects';

vi.mock('@/api/projects', async (importOriginal) => ({
  ...(await importOriginal<Record<string, unknown>>()),
  updateProgress: vi.fn(),
}));

function makeGate() {
  let resolve!: () => void;
  const promise = new Promise<void>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

function renderUpdater() {
  const qc = new QueryClient();
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  return renderHook(() => useUpdateProgress(), { wrapper });
}

describe('useUpdateProgress serialization', () => {
  it('queues writes per project so rapid changes commit in key order', async () => {
    const gates = [makeGate(), makeGate()];
    const seen: Array<{ id: string; progress: string }> = [];
    vi.mocked(updateProgress).mockImplementation(async (id, progress) => {
      seen.push({ id, progress });
      await gates[seen.length - 1].promise;
    });

    const { result } = renderUpdater();
    act(() => {
      result.current.mutate({ id: 's1', progress: 'learning' });
      result.current.mutate({ id: 's1', progress: 'mastered' });
    });

    await waitFor(() => expect(seen).toHaveLength(1));
    expect(seen[0]).toEqual({ id: 's1', progress: 'learning' });

    gates[0].resolve();
    await waitFor(() => expect(seen).toHaveLength(2));
    expect(seen[1]).toEqual({ id: 's1', progress: 'mastered' });
    // Release the project's tail promise so the module-level queue drains
    // before the next test (which uses fresh project ids regardless).
    gates[1].resolve();
  });

  it('does not serialize writes across different projects', async () => {
    const gates = [makeGate(), makeGate()];
    const seen: string[] = [];
    vi.mocked(updateProgress).mockImplementation(async (id) => {
      seen.push(id);
      await gates[seen.length - 1].promise;
    });

    const { result } = renderUpdater();
    act(() => {
      result.current.mutate({ id: 'q1', progress: 'learning' });
      result.current.mutate({ id: 'q2', progress: 'learning' });
    });

    await waitFor(() => expect(seen).toEqual(['q1', 'q2']));
    gates[0].resolve();
    gates[1].resolve();
  });
});
