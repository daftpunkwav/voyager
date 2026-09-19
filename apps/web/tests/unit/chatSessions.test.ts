/**
 * @file chatSessions
 * @description Multi-session store behavior: lane archive/hydrate on switch,
 * per-session SSE routing (inactive-lane messages land in their snapshot),
 * and session-less events staying global.
 */

import { beforeAll, beforeEach, describe, expect, it } from 'vitest';

import { useChatStore, type ChatEvent } from '@/stores/chatStore';
import { initI18n } from '@/i18n';

function ev(seq: number, type: string, payload: Record<string, unknown>): ChatEvent {
  return { seq, type, payload };
}

beforeAll(() => {
  initI18n();
});

beforeEach(() => {
  useChatStore.setState({
    sessions: [],
    activeSessionId: '',
    activeLoaded: false,
    lanes: {},
    messages: [],
    hasMoreHistory: false,
    historyLoading: false,
    cards: {},
    cardOrder: [],
    artifacts: [],
    question: null,
    connected: false,
    thinking: false,
    currentStep: null,
    steps: [],
    trails: [],
    lastSteps: [],
    streaming: null,
  });
});

describe('chatStore multi-session', () => {
  it('switchSession archives the open view and hydrates the target lane', () => {
    const store = useChatStore.getState();
    store.setSessions(
      [
        { session_id: 'a', title: 'A', status: 'waiting_input', active: true },
        { session_id: 'b', title: 'B', status: 'stored' },
      ],
      'a'
    );
    useChatStore.setState({ activeLoaded: true });
    useChatStore.getState().appendLocal({ seq: -1, role: 'user', content: 'hello a' });

    const wasLoaded = useChatStore.getState().switchSession('b');
    expect(wasLoaded).toBe(false);
    const s = useChatStore.getState();
    expect(s.activeSessionId).toBe('b');
    expect(s.messages).toEqual([]); // fresh lane
    expect(s.lanes.a.messages).toHaveLength(1); // archived
    expect(s.lanes.a.thinking).toBe(true); // archived state preserved

    // Switch back: the archive hydrates, loaded flag included
    const loadedAgain = useChatStore.getState().switchSession('a');
    expect(loadedAgain).toBe(true);
    expect(useChatStore.getState().messages).toHaveLength(1);
  });

  it('routes events stamped with an inactive session into that lane', () => {
    const store = useChatStore.getState();
    store.setSessions(
      [
        { session_id: 'a', title: 'A', status: 'waiting_input' },
        { session_id: 'b', title: 'B', status: 'stored' },
      ],
      'a'
    );
    // Give lane b an archived view with a pending turn
    useChatStore.getState().switchSession('b');
    useChatStore.getState().appendLocal({ seq: -2, role: 'user', content: 'question for b' });
    useChatStore.getState().switchSession('a');

    // A reply for the background lane b lands in its snapshot, not the view
    useChatStore
      .getState()
      .dispatch(ev(10, 'agent.message', { content: 'answer for b', session: 'b' }));
    const s = useChatStore.getState();
    expect(s.messages).toHaveLength(0); // active view untouched
    expect(s.lanes.b.messages).toHaveLength(2);
    expect(s.lanes.b.thinking).toBe(false); // reply cleared the lane's turn

    // Opening b shows the reply
    useChatStore.getState().switchSession('b');
    expect(useChatStore.getState().messages.map((m) => m.content)).toEqual([
      'question for b',
      'answer for b',
    ]);
  });

  it('session-less events stay global in the active view', () => {
    const store = useChatStore.getState();
    store.setSessions([{ session_id: 'a', title: 'A', status: 'waiting_input' }], 'a');
    useChatStore.getState().dispatch(ev(11, 'agent.message', { content: 'task done' }));
    expect(useChatStore.getState().messages.map((m) => m.content)).toEqual(['task done']);
  });

  it('streaming deltas for the active session accumulate in the view', () => {
    const store = useChatStore.getState();
    store.setSessions([{ session_id: 'a', title: 'A', status: 'waiting_input' }], 'a');
    // Deltas stream only mid-turn: the thinking flag is raised by the send
    // (appendLocal / the user.message echo) before any delta arrives.
    useChatStore.setState({ thinking: true });
    useChatStore.getState().dispatch(ev(12, 'agent.delta', { text: '你', round: 1, session: 'a' }));
    useChatStore.getState().dispatch(ev(13, 'agent.delta', { text: '好', round: 1, session: 'a' }));
    expect(useChatStore.getState().streaming?.text).toBe('你好');
  });

  it('ask dialogs follow their session: archived with the lane, restored on return', () => {
    const store = useChatStore.getState();
    store.setSessions(
      [
        { session_id: 'a', title: 'A', status: 'waiting_input' },
        { session_id: 'b', title: 'B', status: 'stored' },
      ],
      'a'
    );
    // A question arrives for the active session a
    useChatStore
      .getState()
      .dispatch(ev(20, 'agent.ask', { question_id: 'q1', prompt: 'A 的问题', kind: 'confirm' }));
    expect(useChatStore.getState().question?.questionId).toBe('q1');

    // Switching away must not show A's dialog over session b
    useChatStore.getState().switchSession('b');
    expect(useChatStore.getState().question).toBeNull();

    // While b is open, a question from the background session a parks in
    // its lane instead of hijacking the view
    useChatStore.getState().dispatch(
      ev(21, 'agent.ask', {
        question_id: 'q2',
        prompt: 'A 后台的问题',
        kind: 'choice',
        session: 'a',
      })
    );
    expect(useChatStore.getState().question).toBeNull();
    expect(useChatStore.getState().lanes.a.question?.questionId).toBe('q2');

    // Returning to a restores its latest dialog (the background one)
    useChatStore.getState().switchSession('a');
    expect(useChatStore.getState().question?.questionId).toBe('q2');
  });

  it('a lane reply settles the lane pending question without touching the view', () => {
    const store = useChatStore.getState();
    store.setSessions(
      [
        { session_id: 'a', title: 'A', status: 'waiting_input' },
        { session_id: 'b', title: 'B', status: 'stored' },
      ],
      'a'
    );
    useChatStore.getState().switchSession('b');
    useChatStore
      .getState()
      .dispatch(ev(30, 'agent.ask', { question_id: 'qb', prompt: 'B 的问题', kind: 'confirm' }));
    useChatStore.getState().switchSession('a');

    // The final message for the background lane clears the lane's question
    useChatStore.getState().dispatch(ev(31, 'agent.message', { content: 'done', session: 'b' }));
    expect(useChatStore.getState().lanes.b.question).toBeNull();
    expect(useChatStore.getState().question).toBeNull();
  });
});
