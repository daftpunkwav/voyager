/**
 * @file quotaGuard
 * @description Pre-send daily token quota guard unit tests (phase-67):
 * evaluateQuota pure-function decisions (unlimited / below threshold / ≥80%
 * warn / full block), fetchQuotaGuard soft-fails open (query failure lets
 * the send through; the backend metered_llm is the final guard).
 */

import { beforeEach, describe, expect, it, vi } from 'vitest';

const { callCapabilityMock } = vi.hoisted(() => ({
  callCapabilityMock: vi.fn(),
}));

vi.mock('@/bridge/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/bridge/quotaGuard')>()),
  callCapability: callCapabilityMock,
}));

import {
  quotaWarnMessage,
  QUOTA_WARN_RATIO,
  evaluateQuota,
  fetchQuotaGuard,
} from '@/bridge/quotaGuard';
import { initI18n } from '@/i18n';

/** zh resource value of chat:quota.block (copy moved to the chat ns; assertions keep the zh resource value). */
const QUOTA_BLOCK_ZH = '今日 token 配额已用完，可在设置中调高或明日再试';

beforeAll(() => {
  // Quota copy moved to the chat ns: initialize explicitly (default zh-CN)
  initI18n();
});

beforeEach(() => {
  callCapabilityMock.mockReset();
});

describe('evaluateQuota pure-function decisions', () => {
  it('daily_tokens=0 means unlimited → allow', () => {
    expect(evaluateQuota({ tokens_used_today: 98765, daily_tokens: 0 })).toEqual({
      action: 'allow',
    });
  });

  it('50/100 below the threshold → allow', () => {
    expect(evaluateQuota({ tokens_used_today: 50, daily_tokens: 100 })).toEqual({
      action: 'allow',
    });
  });

  it('85/100 ≥80% → warn with ratio', () => {
    expect(evaluateQuota({ tokens_used_today: 85, daily_tokens: 100 })).toEqual({
      action: 'warn',
      ratio: 0.85,
    });
  });

  it('100/100 full → block with reason', () => {
    expect(evaluateQuota({ tokens_used_today: 100, daily_tokens: 100 })).toEqual({
      action: 'block',
      reason: QUOTA_BLOCK_ZH,
    });
  });

  it('over the cap (120/100) also blocks', () => {
    expect(evaluateQuota({ tokens_used_today: 120, daily_tokens: 100 }).action).toBe('block');
  });

  it('negative limit treated as unlimited → allow', () => {
    expect(evaluateQuota({ tokens_used_today: 10, daily_tokens: -1 })).toEqual({
      action: 'allow',
    });
  });

  it('threshold constant is 0.8 (pre-send warning, intentionally different from the usage page 0.9 display threshold)', () => {
    expect(QUOTA_WARN_RATIO).toBe(0.8);
  });
});

describe('quotaWarnMessage copy', () => {
  it('includes the percentage rounded', () => {
    expect(quotaWarnMessage(0.85)).toContain('85%');
    expect(quotaWarnMessage(0.856)).toContain('86%');
  });
});

describe('fetchQuotaGuard', () => {
  it('reads get_resource_quota and decides; full → block', async () => {
    callCapabilityMock.mockResolvedValue({ tokens_used_today: 5000, daily_tokens: 5000 });
    await expect(fetchQuotaGuard()).resolves.toEqual({
      action: 'block',
      reason: QUOTA_BLOCK_ZH,
    });
    expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'get_resource_quota', {});
  });

  it('soft-fails open when the query fails → allow without throwing', async () => {
    callCapabilityMock.mockRejectedValue(new Error('backend down'));
    await expect(fetchQuotaGuard()).resolves.toEqual({ action: 'allow' });
  });
});
