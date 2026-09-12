/**
 * @file usageDashboardLayout
 * @description Usage page layout tests (phase-65): the "today's token quota"
 * block is independent of the llm history stats — it stays visible while
 * getLlmUsage fails or loads, never swallowed by the parent empty/loading
 * states.
 */

import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { initI18n } from '@/i18n';

const { callCapabilityMock } = vi.hoisted(() => ({
  callCapabilityMock: vi.fn(),
}));

vi.mock('@/bridge/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/bridge/client')>()),
  callCapability: callCapabilityMock,
}));

import { LlmUsageDashboard } from '@/components/usage/LlmUsageDashboard';

function renderDashboard() {
  // Retry disabled: failure cases don't wait for exponential backoff
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <LlmUsageDashboard />
    </QueryClientProvider>
  );
}

// Dashboard copy lives in i18n resources; init once so zh-CN assertions hold
beforeAll(() => {
  initI18n();
});

beforeEach(() => {
  callCapabilityMock.mockReset();
});

describe('usage page layout: quota block renders independently (phase-65)', () => {
  it('still shows the today token quota block when getLlmUsage fails', async () => {
    // The component reaches llm.get_usage_stats via api/usage → callCapability
    // (the envelope is unwrapped in the api layer); split by capability name:
    // inject a failure for get_usage_stats while the quota call
    // (agent.get_resource_quota) resolves normally
    callCapabilityMock.mockImplementation((_domain: unknown, name: string) => {
      if (name === 'get_usage_stats') return Promise.reject(new Error('boom'));
      return Promise.resolve({ tokens_used_today: 1200, daily_tokens: 5000 });
    });
    renderDashboard();

    // Quota block (its own query succeeds) stays visible
    expect(await screen.findByText(/已用 1\.2K/)).toBeInTheDocument();
    expect(screen.getByText('今日 token 配额')).toBeInTheDocument();
    // llm history stats fall into their own empty state without covering the quota block
    expect(await screen.findByText('用量统计服务暂不可用')).toBeInTheDocument();
  });

  it('renders the quota block while getLlmUsage is loading, not hidden by the spinner', async () => {
    callCapabilityMock.mockImplementation((_domain: unknown, name: string) => {
      if (name === 'get_usage_stats') return new Promise(() => {}); // never settles
      return Promise.resolve({ tokens_used_today: 120, daily_tokens: 0 });
    });
    renderDashboard();

    expect(await screen.findByText('今日 token 配额')).toBeInTheDocument();
    expect(screen.getByText('加载用量统计中…')).toBeInTheDocument();
  });
});
