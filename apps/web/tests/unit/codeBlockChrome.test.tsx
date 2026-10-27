/**
 * @file codeBlockChrome
 * @description Characterization of the code-block chrome parts: the language
 * badge of a fenced snippet and its clipboard action.
 */

import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

import { CodeBlockCopyButton } from '@/components/common/codeblock/CodeBlockCopyButton';
import { CodeBlockLanguageBadge } from '@/components/common/codeblock/CodeBlockLanguageBadge';
import { initI18n } from '@/i18n';

const writeText = vi.fn();

beforeAll(() => {
  initI18n();
});

beforeEach(() => {
  writeText.mockReset().mockResolvedValue(undefined);
  Object.defineProperty(navigator, 'clipboard', {
    value: { writeText },
    configurable: true,
    writable: true,
  });
});

describe('CodeBlockLanguageBadge', () => {
  it('shows the fence language', () => {
    render(<CodeBlockLanguageBadge lang="python" />);

    expect(screen.getByText('python')).toBeTruthy();
  });

  it('renders no badge for an unlabeled fence', () => {
    const { container } = render(<CodeBlockLanguageBadge lang={null} />);

    expect(container.firstChild).toBeNull();
  });
});

describe('CodeBlockCopyButton', () => {
  it('copies the source and acknowledges it', async () => {
    render(<CodeBlockCopyButton text="print(1)" />);

    await act(async () => {
      fireEvent.click(screen.getByLabelText('复制代码'));
    });

    expect(writeText).toHaveBeenCalledWith('print(1)');
    expect(screen.getByText('已复制')).toBeTruthy();
  });

  it('keeps the copy label when the clipboard is unavailable', async () => {
    writeText.mockRejectedValue(new Error('denied'));
    render(<CodeBlockCopyButton text="print(1)" />);

    await act(async () => {
      fireEvent.click(screen.getByLabelText('复制代码'));
    });

    expect(writeText).toHaveBeenCalledWith('print(1)');
    expect(screen.getByText('复制')).toBeTruthy();
    expect(screen.queryByText('已复制')).toBeNull();
  });
});
