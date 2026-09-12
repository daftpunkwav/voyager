/**
 * @file usageKpiCards
 * @description KPI cards render the backend's real token split (cached /
 * uncached / completion) and never estimate figures the payload lacks: when
 * totals are absent the cache cards show a dash instead of a 30/70 guess.
 */

import { render, screen } from '@testing-library/react';
import { beforeAll, describe, expect, it } from 'vitest';
import type { LlmUsageSummary } from '@/api/types';
import { UsageKpiCards } from '@/components/usage/UsageKpiCards';
import { initI18n } from '@/i18n';

beforeAll(() => {
  initI18n();
});

/** Shape returned by llm.get_usage_stats (see packages/llm store.usage_stats). */
const REAL_PAYLOAD: LlmUsageSummary = {
  total_input_tokens: 150,
  total_output_tokens: 50,
  totals: {
    input_tokens: 150,
    output_tokens: 50,
    total_tokens: 200,
    prompt_cached_tokens: 30,
    prompt_uncached_tokens: 120,
    completion_tokens: 50,
    calls: 2,
  },
  top: { model: 'm1', total_tokens: 140 },
  by_model: [
    { model: 'm1', input: 100, output: 40, total_tokens: 140, calls: 1 },
    { model: 'm2', input: 50, output: 10, total_tokens: 60, calls: 1 },
  ],
  by_day: [],
};

describe('UsageKpiCards', () => {
  it('shows the reported cache split verbatim', () => {
    render(<UsageKpiCards usage={REAL_PAYLOAD} />);
    expect(screen.getByText('200')).toBeInTheDocument();
    expect(screen.getByText('30')).toBeInTheDocument();
    expect(screen.getByText('120')).toBeInTheDocument();
    expect(screen.getByText('50')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(screen.getByText('unknown/m1')).toBeInTheDocument();
  });

  it('renders a dash instead of estimating when totals are missing', () => {
    const legacy: LlmUsageSummary = {
      total_input_tokens: 1000,
      total_output_tokens: 400,
      by_model: [],
      by_day: [],
    };
    render(<UsageKpiCards usage={legacy} />);
    expect(screen.getByText('1.4K')).toBeInTheDocument();
    expect(screen.getAllByText('—')).toHaveLength(4); // cached, uncached, calls, top model
    expect(screen.queryByText('300')).toBeNull(); // the old 30% guess of 1000
    expect(screen.queryByText('700')).toBeNull();
  });
});
