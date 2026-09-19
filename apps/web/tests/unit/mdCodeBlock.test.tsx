/**
 * @file mdCodeBlock
 * @description MdCodeBlock run lifecycle (the registry is stubbed): changing
 * the text or unmounting while a run is in flight cancels the engine handle,
 * and the stale run's late result never renders (generation guard); stopping
 * surfaces the engine's cancelled status pill.
 */

import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const { getRunnerMock, isRunnableMock, runMock } = vi.hoisted(() => ({
  getRunnerMock: vi.fn(),
  isRunnableMock: vi.fn(),
  runMock: vi.fn(),
}));

vi.mock('@/lib/code-runner', () => ({
  isRunnable: isRunnableMock,
  getRunner: getRunnerMock,
}));

import { MdCodeBlock } from '@/components/common/MdCodeBlock';
import { initI18n } from '@/i18n';

beforeAll(() => {
  initI18n();
});

beforeEach(() => {
  isRunnableMock.mockReset().mockReturnValue(true);
  getRunnerMock.mockReset();
  runMock.mockReset();
});

describe('MdCodeBlock run lifecycle', () => {
  it('a text change while a run is in flight cancels it and drops the late result', async () => {
    let settle!: (outcome: unknown) => void;
    const cancel = vi.fn();
    getRunnerMock.mockReturnValue({
      id: 'python',
      run: runMock.mockReturnValue({
        done: new Promise((resolve) => {
          settle = resolve;
        }),
        cancel,
      }),
    });
    const { rerender } = render(
      <MdCodeBlock lang="python" text="print(1)">
        <code>print(1)</code>
      </MdCodeBlock>
    );
    fireEvent.click(screen.getByLabelText('运行'));
    expect(await screen.findByLabelText('停止')).toBeTruthy();

    // Editing the snippet resets the execution state and cancels the engine...
    rerender(
      <MdCodeBlock lang="python" text="print(2)">
        <code>print(2)</code>
      </MdCodeBlock>
    );
    expect(cancel).toHaveBeenCalled();
    expect(screen.queryByLabelText('停止')).toBeNull(); // back to the idle chrome

    // ...and the stale run's late result must never surface as output
    await act(async () => {
      settle({ status: 'ok', output: 'stale output', durationMs: 1, truncated: false });
    });
    expect(screen.queryByText('stale output')).toBeNull();
    expect(screen.queryByText('输出')).toBeNull();
  });

  it('unmounting while a run is in flight cancels the handle', () => {
    const cancel = vi.fn();
    getRunnerMock.mockReturnValue({
      id: 'python',
      run: runMock.mockReturnValue({ done: new Promise(() => {}), cancel }),
    });
    const { unmount } = render(
      <MdCodeBlock lang="python" text="while True: pass">
        <code>x</code>
      </MdCodeBlock>
    );
    fireEvent.click(screen.getByLabelText('运行'));
    unmount();
    expect(cancel).toHaveBeenCalled();
  });

  it('stopping surfaces the engine-settled cancelled status pill', async () => {
    let settle!: (outcome: unknown) => void;
    // A real engine resolves `done` with a cancelled outcome after cancel();
    // the pill must show that verdict (not a silent reset to idle).
    const cancel = vi.fn(() =>
      settle({ status: 'cancelled', output: '', durationMs: 3, truncated: false })
    );
    getRunnerMock.mockReturnValue({
      id: 'python',
      run: runMock.mockReturnValue({
        done: new Promise((resolve) => {
          settle = resolve;
        }),
        cancel,
      }),
    });
    render(
      <MdCodeBlock lang="python" text="while True: pass">
        <code>x</code>
      </MdCodeBlock>
    );
    fireEvent.click(screen.getByLabelText('运行'));
    fireEvent.click(await screen.findByLabelText('停止'));
    await screen.findByText(/已取消/); // done settles on a microtask after the click
    const pill = screen.getByRole('status');
    expect(pill.textContent).toContain('已取消');
  });
});
