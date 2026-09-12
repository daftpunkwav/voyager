/**
 * @file resumableList
 * @description Phase-70 A unit tests: the team page resumable task list.
 * List rendering, resume (resume_run continue_run=true), abandon (confirm +
 * abandon), the empty state, and retry on load failure.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const { callCapabilityMock } = vi.hoisted(() => ({ callCapabilityMock: vi.fn() }));

// Keep the real ServiceError (the failure branch's error toast goes through extractErrorMessage)
vi.mock('@/bridge/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/bridge/client')>()),
  callCapability: callCapabilityMock,
}));

import { ResumableList } from '@/pages/team/ResumableList';
import { useUIStore } from '@/stores/uiStore';
import { initI18n } from '@/i18n';

beforeAll(() => {
  // EmptyState's default retry copy uses common:action.retry; the i18n kernel must be ready
  initI18n();
});

/** Stateful mock: items are emptied after abandon / resume succeeds (simulating backend deletion / a finished resume) */
let items: Array<Record<string, unknown>> = [];

function backend(_domain: string, name: string, args: Record<string, unknown>) {
  switch (name) {
    case 'list_resumable_checkpoints':
      return Promise.resolve({ items });
    case 'resume_run':
    case 'abandon_resumable_checkpoint':
      items = items.filter((i) => i.run_id !== args.run_id);
      return Promise.resolve(
        name === 'resume_run'
          ? { resumed: 'inst1', run_id: args.run_id, status: 'running', continuing: true }
          : { abandoned: args.run_id }
      );
    default:
      return Promise.resolve({});
  }
}

function sampleItem(overrides: Record<string, unknown> = {}) {
  return {
    run_id: 'runresum001',
    status: 'paused',
    goal: 'Index the whole repo and produce a manifest covering every module',
    instance_name: 'scout',
    started_ts: Math.floor(Date.now() / 1000) - 120,
    last_step: 'round 1: listed dirs',
    mode: 'react',
    ...overrides,
  };
}

beforeEach(() => {
  items = [];
  callCapabilityMock.mockReset();
  callCapabilityMock.mockImplementation(backend);
  useUIStore.setState({ toasts: [] });
  vi.spyOn(window, 'confirm').mockReturnValue(true);
});

describe('resumable task list (phase-70 A)', () => {
  it('renders entries: name / goal truncation / last_step / run_id', async () => {
    items = [sampleItem()];
    render(<ResumableList />);
    expect(await screen.findByText('scout')).toBeTruthy();
    // goal is truncated to 80 chars with an ellipsis (under 80 here, so it shows in full)
    expect(screen.getByText(/Index the whole repo and produce a manifest/)).toBeTruthy();
    expect(screen.getByText(/当前:round 1/)).toBeTruthy();
    expect(screen.getByText(/runresum001/)).toBeTruthy();
    expect(screen.getByText(/分钟前/)).toBeTruthy();
  });

  it('clicking resume: resume_run (continue_run=true) + success toast + the entry disappears after refresh', async () => {
    items = [sampleItem()];
    render(<ResumableList />);
    fireEvent.click(await screen.findByRole('button', { name: '继续' }));

    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'resume_run', {
        run_id: 'runresum001',
        continue_run: true,
      })
    );
    await waitFor(() =>
      expect(
        useUIStore
          .getState()
          .toasts.some((t) => t.type === 'success' && t.message.includes('已续跑 scout'))
      ).toBe(true)
    );
    await waitFor(() => expect(screen.queryByText('scout')).toBeNull());
    expect(screen.getByText('暂无可恢复任务')).toBeTruthy();
  });

  it('clicking abandon: calls abandon_resumable_checkpoint after confirming + toast + the entry disappears', async () => {
    items = [sampleItem()];
    render(<ResumableList />);
    fireEvent.click(await screen.findByRole('button', { name: '放弃' }));

    expect(window.confirm).toHaveBeenCalled();
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'abandon_resumable_checkpoint', {
        run_id: 'runresum001',
      })
    );
    await waitFor(() =>
      expect(
        useUIStore
          .getState()
          .toasts.some((t) => t.type === 'success' && t.message.includes('已放弃 scout'))
      ).toBe(true)
    );
    await waitFor(() => expect(screen.queryByText('scout')).toBeNull());
  });

  it('status=running: resume is disabled with a tooltip (phase-71 E) while abandon still works', async () => {
    items = [sampleItem({ status: 'running' })];
    render(<ResumableList />);
    const btn = await screen.findByRole('button', { name: '继续' });
    expect(btn.hasAttribute('disabled')).toBe(true);
    expect(btn.getAttribute('title')).toContain('仍在运行中');
    // clicking the disabled button does not trigger resume_run
    fireEvent.click(btn);
    expect(callCapabilityMock).not.toHaveBeenCalledWith('agent', 'resume_run', expect.anything());
    // abandon is unaffected (phase-70 semantics: stop the instance + delete the checkpoint)
    fireEvent.click(screen.getByRole('button', { name: '放弃' }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'abandon_resumable_checkpoint', {
        run_id: 'runresum001',
      })
    );
  });

  it('cancelling the abandon confirm dialog sends no request', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    items = [sampleItem()];
    render(<ResumableList />);
    fireEvent.click(await screen.findByRole('button', { name: '放弃' }));

    expect(callCapabilityMock).not.toHaveBeenCalledWith(
      'agent',
      'abandon_resumable_checkpoint',
      expect.anything()
    );
    expect(screen.getByText('scout')).toBeTruthy();
  });

  it('empty items: the "no resumable tasks" empty state', async () => {
    render(<ResumableList />);
    expect(await screen.findByText('暂无可恢复任务')).toBeTruthy();
  });

  it('load failure: error state + retry restores the list', async () => {
    callCapabilityMock.mockRejectedValue(new Error('backend unreachable'));
    render(<ResumableList />);
    expect(await screen.findByText('可恢复任务加载失败')).toBeTruthy();

    callCapabilityMock.mockImplementation(backend);
    items = [sampleItem()];
    fireEvent.click(screen.getByRole('button', { name: '重试' }));
    expect(await screen.findByText('scout')).toBeTruthy();
  });

  it('orphan entries (resumable=false): no resume button, shown in their own section, abandonable (phase-73 B)', async () => {
    items = [
      sampleItem({
        run_id: 'orphan0001',
        instance_name: 'chat orphan',
        resumable: false,
        conversational: true,
        mode: 'react',
      }),
    ];
    render(<ResumableList />);
    expect(await screen.findByText('chat orphan')).toBeTruthy();
    // the section title appears; the orphan row has only "abandon" and no "resume"
    expect(screen.getByText(/仅可放弃的孤儿断点/)).toBeTruthy();
    expect(screen.queryByRole('button', { name: '继续' })).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: '放弃' }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'abandon_resumable_checkpoint', {
        run_id: 'orphan0001',
      })
    );
  });

  it('orphans and resumable entries share the list: resumable entries keep "resume" (phase-73 B sections)', async () => {
    items = [
      sampleItem({ run_id: 'runresum001' }), // no resumable field → treated as resumable
      sampleItem({
        run_id: 'orphan0002',
        instance_name: 'direct orphan',
        resumable: false,
        mode: 'direct',
      }),
    ];
    render(<ResumableList />);
    expect(await screen.findByText('direct orphan')).toBeTruthy();
    // resumable entries have "resume", orphans do not
    expect(screen.getByRole('button', { name: '继续' })).toBeTruthy();
    const abandonBtns = screen.getAllByRole('button', { name: '放弃' });
    expect(abandonBtns).toHaveLength(2);
  });

  it('in_turn=true: shows the "interrupted mid-turn" secondary copy instead of last_step (phase-73 E)', async () => {
    items = [sampleItem({ in_turn: true, last_step: 'round 1' })];
    render(<ResumableList />);
    expect(await screen.findByText(/中途中断/)).toBeTruthy();
    expect(screen.queryByText(/当前:round 1/)).toBeNull(); // the mid-turn copy takes precedence over last_step
  });
});
