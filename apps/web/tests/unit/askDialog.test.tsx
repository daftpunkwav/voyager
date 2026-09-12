/**
 * @file askDialog
 * @description AskDialog tests preserved from the former chatControls suite:
 * the matched=false answer path still collapses and notifies, and the store
 * clears an unanswered question when agent.message arrives.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { callCapabilityMock } = vi.hoisted(() => ({ callCapabilityMock: vi.fn() }));

vi.mock('@/bridge/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/bridge/client')>()),
  callCapability: callCapabilityMock,
}));

import { AskDialog } from '@/widgets/chat/AskDialog';
import { useChatStore } from '@/stores/chatStore';
import { initI18n } from '@/i18n';

beforeAll(() => {
  initI18n();
});

beforeEach(() => {
  callCapabilityMock.mockReset();
  useChatStore.setState({ messages: [], question: null, thinking: false });
});

describe('AskDialog timeout fallback', () => {
  it('when the answer hits matched=false, it still collapses and notifies instead of hanging forever', async () => {
    callCapabilityMock.mockResolvedValue({ matched: false });
    useChatStore.setState({
      question: {
        questionId: 'q1',
        prompt: '选哪个?',
        kind: 'confirm',
        options: [],
        min: null,
        max: null,
      },
    });
    render(<AskDialog />);
    fireEvent.click(screen.getByRole('button', { name: '确认' }));

    await waitFor(() => expect(useChatStore.getState().question).toBeNull());
    const last = useChatStore.getState().messages.at(-1);
    expect(last?.role).toBe('system');
    expect(last?.content).toContain('已失效');
  });
});

describe('chatStore timeout fallback', () => {
  it('clears the unanswered question when agent.message arrives (the agent continues with the default)', () => {
    useChatStore.setState({
      question: {
        questionId: 'q2',
        prompt: '在吗?',
        kind: 'text',
        options: [],
        min: null,
        max: null,
      },
      thinking: true,
    });
    useChatStore.getState().dispatch({
      seq: 10,
      type: 'agent.message',
      payload: { content: '超时了,我先按默认做。' },
    });
    expect(useChatStore.getState().question).toBeNull();
    expect(useChatStore.getState().thinking).toBe(false);
  });

  it('agent.ask with object-shaped options ({"content": ...} LLM output) normalizes to strings', () => {
    useChatStore.getState().dispatch({
      seq: 11,
      type: 'agent.ask',
      payload: {
        question_id: 'q3',
        prompt: '按什么结构写?',
        kind: 'choice',
        options: [{ content: '三件套' }, { label: '自由发挥' }, '纯字符串', { other: 1 }],
      },
    });
    const q = useChatStore.getState().question;
    expect(q?.options).toEqual(['三件套', '自由发挥', '纯字符串', '{"other":1}']);
  });
});

describe('AskDialog free-form answers', () => {
  it('multi_choice toggles options and submits the picked array', async () => {
    callCapabilityMock.mockResolvedValue({ matched: true });
    useChatStore.setState({
      question: {
        questionId: 'q3',
        prompt: '要哪些?',
        kind: 'multi_choice',
        options: ['海边', '山里', '城市'],
        min: null,
        max: null,
      },
    });
    render(<AskDialog />);
    fireEvent.click(screen.getByRole('button', { name: /海边/ }));
    fireEvent.click(screen.getByRole('button', { name: /城市/ }));
    fireEvent.click(screen.getByRole('button', { name: '提交所选' }));

    await waitFor(() => expect(useChatStore.getState().question).toBeNull());
    const arg = callCapabilityMock.mock.calls[0][2] as { value: string[] };
    expect(arg.value).toEqual(['海边', '城市']);
  });

  it('multi_choice free text becomes an addable custom option', async () => {
    callCapabilityMock.mockResolvedValue({ matched: true });
    useChatStore.setState({
      question: {
        questionId: 'q4',
        prompt: '要哪些?',
        kind: 'multi_choice',
        options: ['海边'],
        min: null,
        max: null,
      },
    });
    render(<AskDialog />);
    fireEvent.change(screen.getByPlaceholderText('也可直接输入自定义回答…'), {
      target: { value: '自家后院' },
    });
    fireEvent.click(screen.getByRole('button', { name: '添加为选项' }));
    // The custom option enters the toggle list and is pre-selected
    fireEvent.click(screen.getByRole('button', { name: '提交所选' }));

    await waitFor(() => expect(useChatStore.getState().question).toBeNull());
    const arg = callCapabilityMock.mock.calls[0][2] as { value: string[] };
    expect(arg.value).toEqual(['自家后院']);
  });

  it('a choice question still offers the permanent free-text answer', async () => {
    callCapabilityMock.mockResolvedValue({ matched: true });
    useChatStore.setState({
      question: {
        questionId: 'q5',
        prompt: '选哪个?',
        kind: 'choice',
        options: ['A', 'B'],
        min: null,
        max: null,
      },
    });
    render(<AskDialog />);
    // Buttons submit the preset; the typed input submits its own text
    fireEvent.change(screen.getByPlaceholderText('也可直接输入自定义回答…'), {
      target: { value: '都不选,自定义路线' },
    });
    fireEvent.click(screen.getByRole('button', { name: '自定义回答' }));

    await waitFor(() => expect(useChatStore.getState().question).toBeNull());
    const arg = callCapabilityMock.mock.calls[0][2] as { value: string };
    expect(arg.value).toBe('都不选,自定义路线');
  });

  it('an unknown kind degrades to the free-text form instead of rendering nothing', async () => {
    callCapabilityMock.mockResolvedValue({ matched: true });
    useChatStore.setState({
      question: {
        questionId: 'q6',
        prompt: '新形态问题',
        kind: 'voice' as unknown as 'text',
        options: [],
        min: null,
        max: null,
      },
    });
    render(<AskDialog />);
    const input = screen.getByPlaceholderText('也可直接输入自定义回答…');
    fireEvent.change(input, { target: { value: '用文字答' } });
    fireEvent.keyDown(input, { key: 'Enter' });

    await waitFor(() => expect(useChatStore.getState().question).toBeNull());
    expect(callCapabilityMock).toHaveBeenCalled();
  });
});

describe('AskDialog rating & labeled slider', () => {
  it('rating stars submit an integer 1-5', async () => {
    callCapabilityMock.mockResolvedValue({ matched: true });
    useChatStore.setState({
      question: {
        questionId: 'q7',
        prompt: '这次体验打几分?',
        kind: 'rating',
        options: [],
        min: null,
        max: null,
      },
    });
    render(<AskDialog />);
    fireEvent.click(screen.getByRole('button', { name: '4 星' }));
    fireEvent.click(screen.getByRole('button', { name: '回答' }));

    await waitFor(() => expect(useChatStore.getState().question).toBeNull());
    const arg = callCapabilityMock.mock.calls[0][2] as { value: number };
    expect(arg.value).toBe(4);
  });

  it('a slider with tick labels submits the picked label text', async () => {
    callCapabilityMock.mockResolvedValue({ matched: true });
    useChatStore.setState({
      question: {
        questionId: 'q8',
        prompt: '满意度',
        kind: 'slider',
        options: ['不满意', '一般', '满意'],
        min: null,
        max: null,
      },
    });
    render(<AskDialog />);
    // Discrete scale: move to the last tick, then answer
    const slider = screen.getByRole('slider');
    fireEvent.change(slider, { target: { value: '3' } });
    fireEvent.click(screen.getByRole('button', { name: '回答' }));

    await waitFor(() => expect(useChatStore.getState().question).toBeNull());
    const arg = callCapabilityMock.mock.calls[0][2] as { value: string };
    expect(arg.value).toBe('满意');
  });
});
