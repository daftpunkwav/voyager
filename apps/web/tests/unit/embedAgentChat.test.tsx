/**
 * @file embedAgentChat
 * @description Phase-68 C unit tests: EmbedAgentChat send ordering. When the
 * quota blocks (sendUserTurn rejects): the input is preserved, no
 * false-positive "sent to main chat" system line is inserted, only an error
 * toast; on success the input is cleared and both the user line and the
 * system line land.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const { sendUserTurnMock } = vi.hoisted(() => ({
  sendUserTurnMock: vi.fn(),
}));

vi.mock('@/bridge/chatSend', () => ({
  sendUserTurn: sendUserTurnMock,
}));

vi.mock('@/hooks/useLlmAvailable', () => ({
  useLlmAvailable: () => 'ok',
}));

import { EmbedAgentChat } from '@/widgets/chat/EmbedAgentChat';
import { useUIStore } from '@/stores/uiStore';
import { initI18n } from '@/i18n';

beforeAll(() => {
  // Component copy moved to the agent ns: initialize explicitly (default zh-CN, assertions keep zh resource values)
  initI18n();
  // jsdom gap: the component's scroll effect needs matchMedia / scrollIntoView
  if (!window.matchMedia) {
    window.matchMedia = ((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    })) as unknown as typeof window.matchMedia;
  }
  Element.prototype.scrollIntoView = () => {};
});

beforeEach(() => {
  sendUserTurnMock.mockReset();
  useUIStore.setState({ toasts: [] });
});

function typeAndSend(text: string) {
  fireEvent.change(screen.getByLabelText('导入助手 对话输入'), { target: { value: text } });
  fireEvent.click(screen.getByRole('button', { name: '发送' }));
}

describe('EmbedAgentChat send ordering (phase-68 C)', () => {
  it('quota block: input preserved, no false-positive system line, only an error toast', async () => {
    sendUserTurnMock.mockRejectedValue(new Error('quota exhausted'));
    const { container } = render(<EmbedAgentChat mode="import" title="导入助手" />);

    typeAndSend('recommend similar projects');
    await waitFor(() => expect(useUIStore.getState().toasts).toHaveLength(1));
    const toast = useUIStore.getState().toasts[0];
    expect(toast.type).toBe('error');
    expect(toast.message).toBe('quota exhausted');

    expect(sendUserTurnMock).toHaveBeenCalledTimes(1);
    expect(sendUserTurnMock).toHaveBeenCalledWith(
      expect.stringContaining('recommend similar projects')
    );
    // Input not lost: the textarea still holds the user's original text
    expect((screen.getByLabelText('导入助手 对话输入') as HTMLTextAreaElement).value).toBe(
      'recommend similar projects'
    );
    // No optimistic lines: no user bubble and no "sent to main chat" system line
    // (the textarea's textContent equals the input text, so detect lines by bubble class instead of queryByText)
    expect(container.querySelector('.embed-msg--user')).toBeNull();
    expect(screen.queryByText('已发到主对话，请打开悬浮窗查看。')).not.toBeInTheDocument();
  });

  it('send success: clears the input and lands the user line plus the "sent to main chat" system line', async () => {
    sendUserTurnMock.mockResolvedValue(undefined);
    render(<EmbedAgentChat mode="import" title="导入助手" />);

    typeAndSend('what types do I star');
    await waitFor(() =>
      expect(screen.getByText('已发到主对话，请打开悬浮窗查看。')).toBeInTheDocument()
    );
    expect(screen.getByText('what types do I star')).toBeInTheDocument();
    expect((screen.getByLabelText('导入助手 对话输入') as HTMLTextAreaElement).value).toBe('');
  });
});
