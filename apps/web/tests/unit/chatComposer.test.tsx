/**
 * @file chatComposer
 * @description Unit tests for the shared ChatComposer widget: Enter sends,
 * Shift+Enter and IME-composing Enter do not, typing forwards to setDraft,
 * and the send button mirrors the sending / llmMissing / empty-draft
 * disable rules.
 */

import { fireEvent, render, screen } from '@testing-library/react';
import { beforeAll, describe, expect, it, vi } from 'vitest';
import { ChatComposer } from '@/widgets/chat/ChatComposer';
import type { UseChatSendReturn } from '@/hooks/useChatSend';
import { initI18n } from '@/i18n';

function makeComposer(overrides: Partial<UseChatSendReturn> = {}): UseChatSendReturn {
  return {
    draft: '',
    setDraft: vi.fn(),
    sending: false,
    llmMissing: false,
    send: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
}

/** Dispatch a real keydown so the component sees it as e.nativeEvent */
function pressEnter(box: HTMLElement, opts: { shift?: boolean; composing?: boolean } = {}) {
  const ev = new KeyboardEvent('keydown', {
    key: 'Enter',
    shiftKey: opts.shift ?? false,
    bubbles: true,
    cancelable: true,
  });
  if (opts.composing) Object.defineProperty(ev, 'isComposing', { value: true });
  fireEvent(box, ev);
}

beforeAll(() => {
  initI18n();
});

describe('ChatComposer', () => {
  it('Enter sends; Shift+Enter and IME-composing Enter do not', () => {
    const composer = makeComposer({ draft: 'hello' });
    render(<ChatComposer composer={composer} placeholder="say" className="box" />);
    const box = screen.getByPlaceholderText('say');

    pressEnter(box);
    expect(composer.send).toHaveBeenCalledTimes(1);

    pressEnter(box, { shift: true });
    pressEnter(box, { composing: true });
    expect(composer.send).toHaveBeenCalledTimes(1);
  });

  it('typing forwards to setDraft', () => {
    const composer = makeComposer();
    render(<ChatComposer composer={composer} placeholder="say" className="box" />);
    fireEvent.change(screen.getByPlaceholderText('say'), { target: { value: 'hi' } });
    expect(composer.setDraft).toHaveBeenCalledWith('hi');
  });

  it('send button stays disabled while empty, sending, or llm-missing', () => {
    const { rerender } = render(
      <ChatComposer composer={makeComposer()} placeholder="say" className="box" />
    );
    expect(screen.getByRole('button', { name: '发送' })).toBeDisabled();

    rerender(
      <ChatComposer
        composer={makeComposer({ draft: 'hi', sending: true })}
        placeholder="say"
        className="box"
      />
    );
    expect(screen.getByRole('button', { name: '发送' })).toBeDisabled();

    rerender(
      <ChatComposer
        composer={makeComposer({ draft: 'hi', llmMissing: true })}
        placeholder="say"
        className="box"
      />
    );
    expect(screen.getByRole('button', { name: '发送' })).toBeDisabled();

    rerender(
      <ChatComposer composer={makeComposer({ draft: 'hi' })} placeholder="say" className="box" />
    );
    expect(screen.getByRole('button', { name: '发送' })).not.toBeDisabled();
  });
});
