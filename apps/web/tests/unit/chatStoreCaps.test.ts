/**
 * @file chatStoreCaps
 * @description Cap tests for the two unbounded growth paths: live
 * AGENT_DELIVERY dispatches and NOTE_CREATED artifacts must stop at
 * DELIVERIES_CAP / ARTIFACTS_CAP, keeping the newest entries, so a
 * long-lived floating window cannot accumulate full answers forever.
 *
 * The task-card cap (CARD_CAP) is pinned here too: settled cards
 * (completed/failed) evict oldest-first, a running card survives while a
 * settled card is still evictable, an all-running set falls through to the
 * front, and pruning never mutates what it was given.
 */

import { beforeEach, describe, expect, it } from 'vitest';
import { EventType } from '@/bridge/events';
import { pruneCards, useChatStore } from '@/stores/chatStore';
import type { ChatEvent, ProgressCard } from '@/stores/chatStore';

function deliveryEvent(seq: number): ChatEvent {
  return {
    seq,
    type: EventType.AGENT_DELIVERY,
    payload: { member: 'elio', name: 'Elio', title: `t${seq}`, content: `answer ${seq}` },
    ts: 1,
  };
}

describe('chatStore delivery/artifact caps', () => {
  beforeEach(() => {
    useChatStore.setState({ deliveries: [], artifacts: [] });
  });

  it('keeps only the newest DELIVERIES_CAP deliveries', () => {
    const { dispatch } = useChatStore.getState();
    for (let seq = 1; seq <= 150; seq++) dispatch(deliveryEvent(seq));

    const deliveries = useChatStore.getState().deliveries;
    expect(deliveries).toHaveLength(100);
    // Newest wins: the survivors are the highest seqs, in arrival order
    expect(deliveries[0].seq).toBe(51);
    expect(deliveries[deliveries.length - 1].seq).toBe(150);
  });

  it('keeps only the newest ARTIFACTS_CAP artifacts without duplicates', () => {
    const { dispatch } = useChatStore.getState();
    for (let seq = 1; seq <= 80; seq++) {
      dispatch({
        seq,
        type: EventType.NOTE_CREATED,
        payload: { note_id: `n${seq}`, title: `note ${seq}` },
        ts: 1,
      });
    }
    // A replayed event must not push a fresh entry out of the window
    dispatch({ seq: 80, type: EventType.NOTE_CREATED, payload: { note_id: 'n80' }, ts: 1 });

    const artifacts = useChatStore.getState().artifacts;
    expect(artifacts).toHaveLength(50);
    expect(artifacts[0].seq).toBe(31);
    expect(artifacts[artifacts.length - 1].seq).toBe(80);
  });
});

describe('chatStore task card cap', () => {
  let seq = 0;

  /** Dispatch one task event (progress/completed/failed) into the store. */
  function dispatchTask(type: string, payload: Record<string, unknown>): void {
    seq += 1;
    useChatStore.getState().dispatch({ seq, type, payload } as ChatEvent);
  }

  beforeEach(() => {
    seq = 0;
    useChatStore.setState({ cards: {}, cardOrder: [] });
  });

  it('evicts the oldest settled cards first once the cap is exceeded', () => {
    dispatchTask(EventType.TASK_FAILED, { job_id: 'f-0', error: 'boom' });
    for (let i = 0; i < 29; i++) dispatchTask(EventType.TASK_COMPLETED, { job_id: `c-${i}` });
    dispatchTask(EventType.TASK_COMPLETED, { job_id: 'c-29' });

    const { cards, cardOrder } = useChatStore.getState();
    expect(cardOrder).toHaveLength(30);
    // A failed card is settled too: the oldest one goes first
    expect(cards['f-0']).toBeUndefined();
    expect(cards['c-0']).toBeDefined();
    // The survivors keep their arrival order
    expect(cardOrder[0]).toBe('c-0');
    expect(cardOrder[cardOrder.length - 1]).toBe('c-29');
  });

  it('keeps a running card even when it is the oldest, as long as a settled card is evictable', () => {
    dispatchTask(EventType.TASK_PROGRESS, { job_id: 'live-0' });
    for (let i = 0; i < 30; i++) dispatchTask(EventType.TASK_COMPLETED, { job_id: `c-${i}` });

    const { cards, cardOrder } = useChatStore.getState();
    expect(cardOrder).toHaveLength(30);
    expect(cardOrder[0]).toBe('live-0');
    expect(cards['live-0']).toMatchObject({ status: 'running' });
    // The settled card was evicted instead of the running one
    expect(cards['c-0']).toBeUndefined();
    expect(cards['c-29']).toBeDefined();
  });

  it('falls through to the front when every card is running', () => {
    for (let i = 0; i < 31; i++) dispatchTask(EventType.TASK_PROGRESS, { job_id: `live-${i}` });

    const { cards, cardOrder } = useChatStore.getState();
    expect(cardOrder).toHaveLength(30);
    // Nothing is settled, so the front card is evicted regardless of status
    expect(cards['live-0']).toBeUndefined();
    expect(cardOrder[0]).toBe('live-1');
    expect(Object.values(cards).every((c) => c.status === 'running')).toBe(true);
  });

  it('keeps every card while the order stays under the cap', () => {
    for (let i = 0; i < 29; i++) dispatchTask(EventType.TASK_COMPLETED, { job_id: `c-${i}` });
    expect(useChatStore.getState().cardOrder).toHaveLength(29);

    dispatchTask(EventType.TASK_COMPLETED, { job_id: 'c-29' });

    const { cards, cardOrder } = useChatStore.getState();
    expect(cardOrder).toHaveLength(30);
    expect(Object.keys(cards)).toHaveLength(30);
    expect(cardOrder[0]).toBe('c-0');
    expect(cards['c-28']).toBeDefined();
  });

  it('returns fresh copies and leaves the given cards and order untouched', () => {
    const cards: Record<string, ProgressCard> = {};
    const order: string[] = [];
    for (let i = 0; i < 31; i++) {
      const id = `c-${i}`;
      order.push(id);
      cards[id] = { key: id, label: id, progress: 1, stage: 'done', status: 'completed' };
    }

    const next = pruneCards(cards, order);
    expect(next.cards).not.toBe(cards);
    expect(next.order).not.toBe(order);
    expect(Object.keys(next.cards)).toHaveLength(30);
    expect(next.order).toHaveLength(30);
    // The inputs are untouched
    expect(Object.keys(cards)).toHaveLength(31);
    expect(order).toHaveLength(31);
  });
});
