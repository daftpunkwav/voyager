/**
 * @file localeBridge
 * @description Locale single-source tests (design §11.2): syncLocale applies
 * store + html[lang] + i18n idempotently, dirty values fall back to the
 * default, and changeLocale persists via set_setting first — a failed save
 * never switches the UI language.
 */

import { act, renderHook, waitFor } from '@testing-library/react';
import { afterAll, beforeEach, describe, expect, it, vi } from 'vitest';

const { callCapabilityMock } = vi.hoisted(() => ({ callCapabilityMock: vi.fn() }));

vi.mock('@/bridge/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/bridge/client')>()),
  callCapability: callCapabilityMock,
}));

vi.mock('@/bridge/stream', () => ({
  subscribe: vi.fn(() => () => {}),
}));

import { syncLocale, useLocaleBridge } from '@/shell/localeBridge';
import { useLocale } from '@/hooks/useLocale';
import { useUIStore } from '@/stores/uiStore';
import { initI18n, i18n } from '@/i18n';

/** jsdom navigator.languages is a getter; redefine per test. */
function stubNavigatorLanguages(tags: string[]): void {
  Object.defineProperty(window.navigator, 'languages', {
    value: tags,
    configurable: true,
  });
}

const realLanguages = Object.getOwnPropertyDescriptor(window.navigator, 'languages');
afterAll(() => {
  if (realLanguages) {
    Object.defineProperty(window.navigator, 'languages', realLanguages);
  }
});

beforeEach(() => {
  initI18n();
  void i18n.changeLanguage('zh-CN');
  callCapabilityMock.mockReset();
  callCapabilityMock.mockResolvedValue({});
  window.localStorage.clear();
  useUIStore.setState({ locale: 'zh-CN' });
  document.documentElement.lang = 'zh-CN';
});

describe('localeBridge (syncLocale single source)', () => {
  it("syncLocale('en') aligns store + html[lang] + i18n in one step", async () => {
    act(() => syncLocale('en'));
    expect(useUIStore.getState().locale).toBe('en');
    expect(document.documentElement.lang).toBe('en');
    await waitFor(() => expect(i18n.language).toBe('en'));
  });

  it('repeated calls are idempotent with no side-effect accumulation', async () => {
    act(() => syncLocale('en'));
    act(() => syncLocale('en'));
    expect(document.documentElement.lang).toBe('en');
    await waitFor(() => expect(i18n.language).toBe('en'));
  });

  it('dirty values fall back to the default zh-CN without throwing', () => {
    act(() => syncLocale('jp'));
    expect(useUIStore.getState().locale).toBe('zh-CN');
    expect(document.documentElement.lang).toBe('zh-CN');
  });

  it("syncLocale('system') keeps the system choice and resolves lang to a concrete locale", () => {
    stubNavigatorLanguages(['en-US', 'zh-CN']);
    act(() => syncLocale('system'));
    expect(useUIStore.getState().locale).toBe('system');
    expect(document.documentElement.lang).toBe('en');
  });
});

describe('useLocaleBridge (startup sync)', () => {
  it('switches to English at startup when get_setting returns en', async () => {
    callCapabilityMock.mockResolvedValue({ key: 'appearance.locale', value: 'en' });
    renderHook(() => useLocaleBridge());
    await waitFor(() => expect(document.documentElement.lang).toBe('en'));
    await waitFor(() => expect(i18n.language).toBe('en'));
  });

  it('keeps the local choice without crashing the shell when the backend is unreachable', async () => {
    callCapabilityMock.mockRejectedValue(new Error('unreachable'));
    useUIStore.setState({ locale: 'en' });
    renderHook(() => useLocaleBridge());
    await waitFor(() => expect(callCapabilityMock).toHaveBeenCalled());
    expect(document.documentElement.lang).toBe('zh-CN'); // untouched by the startup flow
    expect(useUIStore.getState().locale).toBe('en');
  });
});

describe('useLocale (changeLocale single write path)', () => {
  it('persists via set_setting first, then syncs locally on success', async () => {
    const { result } = renderHook(() => useLocale());
    await act(async () => {
      await result.current.changeLocale('en');
    });
    expect(callCapabilityMock).toHaveBeenCalledWith('settings', 'set_setting', {
      key: 'appearance.locale',
      value: 'en',
    });
    expect(useUIStore.getState().locale).toBe('en');
    expect(document.documentElement.lang).toBe('en');
  });

  it("changeLocale('system') passes system through to the backend and resolves lang to a concrete value", async () => {
    stubNavigatorLanguages(['zh-CN']);
    const { result } = renderHook(() => useLocale());
    await act(async () => {
      await result.current.changeLocale('system');
    });
    expect(callCapabilityMock).toHaveBeenCalledWith('settings', 'set_setting', {
      key: 'appearance.locale',
      value: 'system',
    });
    expect(useUIStore.getState().locale).toBe('system');
    expect(document.documentElement.lang).toBe('zh-CN');
  });

  it('does not switch the language when saving fails (choice/DOM/i18n all untouched)', async () => {
    callCapabilityMock.mockRejectedValue(new Error('save failed'));
    const { result } = renderHook(() => useLocale());
    await expect(
      act(async () => {
        await result.current.changeLocale('en');
      })
    ).rejects.toThrow('save failed');
    expect(useUIStore.getState().locale).toBe('zh-CN');
    expect(document.documentElement.lang).toBe('zh-CN');
    await waitFor(() => expect(i18n.language).toBe('zh-CN'));
  });
});
