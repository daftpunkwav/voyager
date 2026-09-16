/**
 * @file i18nMissingKey
 * @description Missing-key resilience (design G4): a missing key never blanks
 * the UI — it falls back to zh-CN, then to the key itself. Also pins
 * initI18n() idempotency and the inlined bundle wiring.
 */

import { describe, expect, it } from 'vitest';
import i18next from 'i18next';
import { initI18n, i18n } from '@/i18n';
import { DEFAULT_LOCALE } from '@/i18n/config';

describe('i18n bootstrap and missing-key fallback', () => {
  it('initI18n is idempotent: repeated calls return the same instance and keep the language', () => {
    expect(initI18n()).toBe(initI18n());
    expect(i18n.isInitialized).toBe(true);
  });

  it('the default Chinese bundle works (flat keys hit as-is)', () => {
    expect(i18n.t('shell:nav.settings')).toBe('设置');
    expect(i18n.t('settings:appearance.title')).toBe('外观');
  });

  it('returns the key itself when the current language lacks it (never blank)', () => {
    expect(i18n.t('common:nope.missing_key')).toBe('nope.missing_key');
  });

  it('missing keys fall back to fallbackLng (zh-CN)', () => {
    // Separate instance builds an imbalance where the en bundle misses the key (global bundles are parity-checked by i18n:check)
    const inst = i18next.createInstance();
    void inst.init({
      lng: 'en',
      fallbackLng: DEFAULT_LOCALE,
      resources: {
        'zh-CN': { t: { 'only.zh': '中文值' } },
        en: { t: {} },
      },
      keySeparator: false,
      nsSeparator: ':',
      initImmediate: false,
    });
    expect(inst.t('t:only.zh')).toBe('中文值');
  });

  it('t() follows changeLanguage (en)', async () => {
    await i18n.changeLanguage('en');
    expect(i18n.t('shell:nav.settings')).toBe('Settings');
    await i18n.changeLanguage('zh-CN');
    expect(i18n.t('shell:nav.settings')).toBe('设置');
  });
});
