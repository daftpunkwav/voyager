/**
 * @file llmAgentOverrides
 * @description Per-agent override table (LLM settings): provider/model/style
 * edits persist straight to the agent.llm.overrides and agent.style.overrides
 * settings keys; entries whose provider AND model are both cleared are dropped
 * from the stored map instead of persisting empty objects.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const { callCapabilityMock, setCalls } = vi.hoisted(() => ({
  callCapabilityMock: vi.fn(),
  setCalls: [] as Array<{ key: string; value: unknown }>,
}));

vi.mock('@/bridge/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/bridge/client')>()),
  callCapability: callCapabilityMock,
}));

import { LlmAgentOverrides } from '@/components/settings/llm/LlmAgentOverrides';
import type { LlmProvider } from '@/api/types';
import { initI18n } from '@/i18n';

const PROVIDERS = [
  {
    id: 'p1',
    display_name: 'P One',
    enabled: true,
    models: ['m1', 'm2'],
    models_meta: {},
  },
  {
    id: 'p2',
    display_name: 'P Two',
    enabled: true,
    models: ['m3'],
    models_meta: {},
  },
] as unknown as LlmProvider[];

let storedOverrides: Record<string, unknown> = {};

const setup = () => render(<LlmAgentOverrides providers={PROVIDERS} />);

beforeAll(() => {
  initI18n();
});

beforeEach(() => {
  storedOverrides = {};
  setCalls.length = 0;
  callCapabilityMock.mockReset().mockImplementation((_d: string, name: string, payload?) => {
    if (name === 'get_setting') {
      const key = payload?.key as string;
      return Promise.resolve({ key, value: storedOverrides[key] ?? {} });
    }
    if (name === 'set_setting') {
      setCalls.push({ key: payload?.key, value: payload?.value });
      storedOverrides[payload?.key as string] = payload?.value;
      return Promise.resolve({});
    }
    return Promise.resolve({});
  });
});

/** Opens one row's select (portal menu) and picks the option by text. */
async function pick(ariaLabel: string, optionText: string) {
  // findBy*: the override maps load asynchronously before the table renders
  fireEvent.click(await screen.findByRole('button', { name: ariaLabel }));
  const option = await screen.findByRole('option', { name: optionText });
  fireEvent.click(option);
}

describe('LlmAgentOverrides', () => {
  it('persists a provider pick to agent.llm.overrides with the model cleared', async () => {
    setup();
    await pick('Lucien 供应商', 'P One');
    await waitFor(() => expect(setCalls.some((c) => c.key === 'agent.llm.overrides')).toBe(true));
    const call = setCalls.find((c) => c.key === 'agent.llm.overrides')!;
    expect(call.value).toEqual({ orchestrator: { provider: 'p1', model: '' } });
  });

  it('drops the whole entry when provider and model are both back on default', async () => {
    storedOverrides = { 'agent.llm.overrides': { orchestrator: { provider: 'p1', model: 'm1' } } };
    setup();
    // the stored provider shows as the trigger value; switch back to default
    await pick('Lucien 供应商', '默认（P One）');
    await waitFor(() => expect(setCalls.some((c) => c.key === 'agent.llm.overrides')).toBe(true));
    const call = setCalls.find((c) => c.key === 'agent.llm.overrides')!;
    expect(call.value).toEqual({});
  });

  it('persists a style pick to agent.style.overrides', async () => {
    setup();
    await pick('Lucien 说话风格', '毒舌');
    await waitFor(() => expect(setCalls.some((c) => c.key === 'agent.style.overrides')).toBe(true));
    const call = setCalls.find((c) => c.key === 'agent.style.overrides')!;
    expect(call.value).toEqual({ orchestrator: '毒舌' });
  });
});
