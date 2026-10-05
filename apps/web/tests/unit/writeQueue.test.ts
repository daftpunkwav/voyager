/**
 * @file writeQueue
 * @description Locks the per-key write queue used for progress updates: rapid
 * writes to one key reach the writer strictly in call order (an older write
 * can never land last), a failed write does not poison the queue, and
 * different keys stay independent.
 */

import { describe, expect, it, vi } from 'vitest';
import { createKeyedWriteQueue } from '@/utils/writeQueue';

function makeGate() {
  let resolve!: () => void;
  const promise = new Promise<void>((r) => {
    resolve = r;
  });
  return { promise, resolve };
}

describe('keyed write queue', () => {
  it('chains writes per key so rapid updates commit in call order', async () => {
    const gates = [makeGate(), makeGate()];
    const seen: Array<[string, number]> = [];
    const write = vi.fn((...args: [string, number]) => {
      seen.push(args);
      return gates[seen.length - 1].promise;
    });
    const enqueue = createKeyedWriteQueue(write);

    const first = enqueue('p1', 1);
    const second = enqueue('p1', 2);

    await vi.waitFor(() => expect(seen).toEqual([['p1', 1]]));
    gates[0].resolve();
    await first;
    await vi.waitFor(() =>
      expect(seen).toEqual([
        ['p1', 1],
        ['p1', 2],
      ])
    );
    gates[1].resolve();
    await second;
    expect(seen).toEqual([
      ['p1', 1],
      ['p1', 2],
    ]);
  });

  it('keeps the queue flowing after a failed write', async () => {
    const seen: string[] = [];
    const write = vi.fn((id: string, progress: number) => {
      seen.push(`${id}:${progress}`);
      if (progress === 1) return Promise.reject(new Error('write failed'));
      return Promise.resolve();
    });
    const enqueue = createKeyedWriteQueue(write);

    await enqueue('f1', 1).catch(() => {});
    await enqueue('f1', 2);
    expect(seen).toEqual(['f1:1', 'f1:2']);
  });

  it('does not serialize writes across different keys', async () => {
    const gates = [makeGate(), makeGate()];
    const seen: string[] = [];
    const write = vi.fn((id: string) => {
      seen.push(id);
      return gates[seen.length - 1].promise;
    });
    const enqueue = createKeyedWriteQueue(write);

    const first = enqueue('q1');
    const second = enqueue('q2');
    await vi.waitFor(() => expect(seen).toEqual(['q1', 'q2']));

    gates[0].resolve();
    await first;
    gates[1].resolve();
    await second;
  });
});
