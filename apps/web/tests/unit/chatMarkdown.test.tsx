/**
 * @file chatMarkdown
 * @description Chat markdown rendering: GFM tables get the scroll wrapper,
 * code fences get the shared block chrome (language label / copy / run),
 * the run button is gated by language and the runCode prop, and mermaid
 * fences route into MermaidBlock.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, beforeAll, describe, expect, it, vi } from 'vitest';

const { getRunnerMock, isRunnableMock, runMock } = vi.hoisted(() => ({
  getRunnerMock: vi.fn(),
  isRunnableMock: vi.fn(),
  runMock: vi.fn(),
}));

vi.mock('@/components/common/MermaidBlock', () => ({
  looksLikeMermaid: (lang: string | null | undefined) => (lang || '').toLowerCase() === 'mermaid',
  MermaidBlock: ({ code }: { code: string }) => <div data-testid="mermaid-stub">{code}</div>,
}));

vi.mock('@/lib/code-runner', () => ({
  isRunnable: isRunnableMock,
  getRunner: getRunnerMock,
}));

import { ChatMarkdown } from '@/widgets/chat/ChatMarkdown';
import { initI18n } from '@/i18n';

beforeAll(() => {
  initI18n();
});

beforeEach(() => {
  isRunnableMock.mockReset();
  getRunnerMock.mockReset();
  runMock.mockReset();
  // Default: no language is executable (per-test setups opt in)
  isRunnableMock.mockReturnValue(false);
});

describe('ChatMarkdown tables', () => {
  it('wraps GFM tables in the horizontal-scroll wrapper', () => {
    const { container } = render(
      <ChatMarkdown
        content={['| 维度 | 多线程 |', '| --- | --- |', '| 内存 | 共享 |'].join('\n')}
      />
    );
    const wrap = container.querySelector('.markdown-table-wrap');
    expect(wrap).not.toBeNull();
    expect(wrap?.querySelectorAll('th')).toHaveLength(2);
    expect(screen.getByText('多线程')).toBeTruthy();
  });
});

describe('ChatMarkdown code blocks', () => {
  it('renders a fenced block with language label and copy button', () => {
    render(<ChatMarkdown content={'```python\nprint(1)\n```'} />);
    expect(document.querySelector('.md-codeblock')).not.toBeNull();
    expect(screen.getByText('python')).toBeTruthy();
    expect(screen.getByLabelText('复制代码')).toBeTruthy();
    expect(screen.queryByLabelText('运行')).toBeNull(); // runnable=false by default stub
  });

  it('shows the run button only for runnable languages', () => {
    isRunnableMock.mockImplementation((lang?: string) => (lang ?? '') === 'python');
    render(<ChatMarkdown content={'```python\nprint(1)\n```'} />);
    expect(screen.getByLabelText('运行')).toBeTruthy();
  });

  it('omits the run button when runCode is false (trace views)', () => {
    isRunnableMock.mockReturnValue(true);
    render(<ChatMarkdown content={'```python\nprint(1)\n```'} runCode={false} />);
    expect(screen.queryByLabelText('运行')).toBeNull();
  });

  it('runs the snippet through the registry and shows the output panel', async () => {
    isRunnableMock.mockReturnValue(true);
    getRunnerMock.mockReturnValue({
      id: 'python',
      run: runMock.mockReturnValue({
        done: Promise.resolve({
          status: 'ok',
          output: 'hello\n',
          durationMs: 12,
          truncated: false,
        }),
        cancel: vi.fn(),
      }),
    });
    render(<ChatMarkdown content={'```python\nprint("hello")\n```'} />);
    fireEvent.click(screen.getByLabelText('运行'));
    await waitFor(() => expect(screen.getByRole('status')).toBeTruthy());
    const outputPre = document.querySelector('.md-codeblock__output-pre');
    expect(outputPre?.textContent).toContain('hello');
    expect(screen.getByText(/完成/)).toBeTruthy();
    expect(runMock).toHaveBeenCalledWith('print("hello")');
  });

  it('stop button appears while a run is in flight and cancels it', async () => {
    isRunnableMock.mockReturnValue(true);
    const cancel = vi.fn();
    getRunnerMock.mockReturnValue({
      id: 'python',
      run: runMock.mockReturnValue({ done: new Promise(() => {}), cancel }),
    });
    render(<ChatMarkdown content={'```python\nwhile True:\n    pass\n```'} />);
    fireEvent.click(screen.getByLabelText('运行'));
    expect(await screen.findByLabelText('停止')).toBeTruthy();
    fireEvent.click(screen.getByLabelText('停止'));
    expect(cancel).toHaveBeenCalled();
    expect(screen.getByText('输出')).toBeTruthy();
  });
});

describe('ChatMarkdown mermaid', () => {
  it('routes mermaid fences into MermaidBlock', () => {
    render(<ChatMarkdown content={'```mermaid\nflowchart TD\nA-->B\n```'} />);
    const stub = screen.getByTestId('mermaid-stub');
    expect(stub.textContent).toContain('flowchart TD');
    expect(document.querySelector('.md-codeblock')).toBeNull();
  });
});
