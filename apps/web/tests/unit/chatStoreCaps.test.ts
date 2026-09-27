/**
 * @file chatStoreCaps
 * @description Cap tests for the two unbounded growth paths: live
 * AGENT_DELIVERY dispatches and NOTE_CREATED artifacts must stop at
 * DELIVERIES_CAP / ARTIFACTS_CAP, keeping the newest entries, so a
 * long-lived floating window cannot accumulate full answers forever.
 */

import { beforeEach, describe, expect, it } from 'vitest';
import { EventType } from '@/bridge/events';
import { useChatStore } from '@/stores/chatStore';
import type { ChatEvent } from '@/stores/chatStore';

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
