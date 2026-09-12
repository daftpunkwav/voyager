/**
 * @file i18nConfig
 * @description Locale model tests: 'system' resolution order, dirty-value
 * fallback and the closed LocaleId guard (design §11.2).
 */

import { describe, expect, it } from 'vitest';
import {
  DEFAULT_LOCALE,
  SUPPORTED_LOCALES,
  isLocaleId,
  normalizeLocaleChoice,
  resolveLocale,
} from '@/i18n/config';

/** jsdom exposes navigator.languages/language as getters; redefine per test. */
function stubNavigator(tags: string[]): void {
  Object.defineProperty(window.navigator, 'languages', {
    value: tags,
    configurable: true,
  });
  Object.defineProperty(window.navigator, 'language', {
    value: tags[0] ?? 'en-US',
    configurable: true,
  });
}

describe('i18n config (locale model)', () => {
  it('defaults to zh-CN with a closed supported set', () => {
    expect(DEFAULT_LOCALE).toBe('zh-CN');
    expect(SUPPORTED_LOCALES).toEqual(['zh-CN', 'en']);
  });

  it('resolveLocale passes concrete locales through', () => {
    expect(resolveLocale('en')).toBe('en');
    expect(resolveLocale('zh-CN')).toBe('zh-CN');
  });

  it("resolveLocale('system') maps to the nearest supported tag in priority order", () => {
    stubNavigator(['en-US', 'zh-CN']);
    expect(resolveLocale('system')).toBe('en');
    stubNavigator(['zh', 'en']);
    expect(resolveLocale('system')).toBe('zh-CN');
    stubNavigator(['fr', 'de']);
    expect(resolveLocale('system')).toBe('zh-CN'); // falls back to the default when nothing matches
  });

  it('normalizes dirty values (unknown strings/numbers/undefined) to the default locale', () => {
    expect(normalizeLocaleChoice('jp')).toBe('zh-CN');
    expect(normalizeLocaleChoice(42)).toBe('zh-CN');
    expect(normalizeLocaleChoice(undefined)).toBe('zh-CN');
    expect(resolveLocale('dirty-value')).toBe('zh-CN');
  });

  it('isLocaleId only accepts registered values', () => {
    expect(isLocaleId('en')).toBe(true);
    expect(isLocaleId('zh-CN')).toBe(true);
    expect(isLocaleId('system')).toBe(false);
    expect(isLocaleId('zh')).toBe(false);
    expect(isLocaleId(null)).toBe(false);
  });
});
