/**
 * @file usageDailyQuota
 * @description Unit tests for the usage page "today's token quota" card
 * (phase-63): mounts agent.observe(quota), verifies the used/limit
 * display, 0 = unlimited draws no progress bar, failure shows the error
 * state without crashing, and the progress bar turns warning-colored at the
 * cap.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { initI18n } from '@/i18n';

const { callCapabilityMock } = vi.hoisted(() => ({
  callCapabilityMock: vi.fn(),
}));

vi.mock('@/bridge/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/bridge/client')>()),
  callCapability: callCapabilityMock,
}));

import { DailyTokenQuotaCard } from '@/components/usage/DailyTokenQuotaCard';

function renderCard() {
  // Retry disabled: failure cases don't wait for exponential backoff
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <DailyTokenQuotaCard />
    </QueryClientProvider>
  );
}

// The card's copy lives in i18n resources; init once so zh-CN assertions hold
beforeAll(() => {
  initI18n();
});

beforeEach(() => {
  callCapabilityMock.mockReset();
});

describe('usage page today token quota (phase-63)', () => {
  it('shows used and limit (1200/5000) and draws a progress bar', async () => {
    callCapabilityMock.mockResolvedValue({ tokens_used_today: 1200, daily_tokens: 5000 });
    renderCard();

    expect(await screen.findByText(/已用 1\.2K/)).toBeInTheDocument();
    expect(screen.getByText(/上限 5\.0K/)).toBeInTheDocument();
    expect(screen.getByText(/服务重启后当日用量仍累计/)).toBeInTheDocument();
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '24');
    expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'observe', { action: 'quota' });
  });

  it('shows "no limit" when daily_tokens=0 and draws no fake progress bar', async () => {
    callCapabilityMock.mockResolvedValue({ tokens_used_today: 500, daily_tokens: 0 });
    renderCard();

    expect(await screen.findByText(/上限 不限/)).toBeInTheDocument();
    expect(screen.getByText(/未设上限，不计进度/)).toBeInTheDocument();
    expect(screen.queryByRole('progressbar')).not.toBeInTheDocument();
  });

  it('shows the error state with retry on capability failure without throwing', async () => {
    callCapabilityMock.mockRejectedValue(new Error('boom'));
    renderCard();

    expect(await screen.findByText(/配额读取失败/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '重试' })).toBeInTheDocument();
  });

  it('progress bar hits 100% and turns warning when usage reaches the cap', async () => {
    callCapabilityMock.mockResolvedValue({ tokens_used_today: 5000, daily_tokens: 5000 });
    renderCard();

    const bar = await screen.findByRole('progressbar');
    await waitFor(() => expect(bar).toHaveAttribute('aria-valuenow', '100'));
    expect(bar.className).toContain('is-warning');
  });
});
