/**
 * @file chatStoreSystemSeq
 * @description Unit tests for the locally synthesized system notices: their
 * seq must be unique and always negative so React keys never collide and
 * applyHistory's `seq < 0` live-bubble guard keeps holding.
 */

import { beforeEach, describe, expect, it } from 'vitest';
import { useChatStore } from '@/stores/chatStore';

describe('chatStore.addSystem seq', () => {
  beforeEach(() => {
    useChatStore.setState({ messages: [] });
  });

  it('assigns unique negative seqs to two notices in the same tick', () => {
    const { addSystem } = useChatStore.getState();
    addSystem('first');
    addSystem('second');

    const [a, b] = useChatStore.getState().messages;
    expect(a.seq).not.toBe(b.seq);
    expect(a.seq).toBeLessThan(0);
    expect(b.seq).toBeLessThan(0);
  });

  it('keeps later notices sorted before earlier ones (strictly decreasing)', () => {
    const { addSystem } = useChatStore.getState();
    addSystem('first');
    addSystem('second');
    addSystem('third');

    const seqs = useChatStore.getState().messages.map((m) => m.seq);
    expect(seqs).toEqual([...seqs].sort((x, y) => y - x));
    expect(new Set(seqs).size).toBe(seqs.length);
  });
});
