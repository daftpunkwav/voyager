/**
 * @file i18nFormat
 * @description Formatting follows the active i18n language (design G6):
 * date/time/relative-time outputs change with changeLanguage, and the
 * utils/date façade keeps its ISO-string contract without hardcoded locales.
 */

import { beforeAll, describe, expect, it } from 'vitest';
import { formatDate, formatDateTime, formatNumber, formatRelativeTime, formatTime } from '@/i18n';
import { formatDateTime as isoDateTime, formatRelativeTime as isoRelative } from '@/utils/date';
import { initI18n, i18n } from '@/i18n';

// Fixed UTC instant; assertions only check language-driven format differences, not timezone-specific clock time
const TS = new Date('2026-05-12T08:00:00Z');

beforeAll(() => {
  initI18n();
  void i18n.changeLanguage('zh-CN');
});

describe('i18n/format (formatting follows language)', () => {
  it('formatDate year/month/day ordering follows language', async () => {
    await i18n.changeLanguage('zh-CN');
    expect(formatDate(TS)).toMatch(/^2026\//);
    await i18n.changeLanguage('en');
    expect(formatDate(TS)).toMatch(/\/2026$/);
    await i18n.changeLanguage('zh-CN');
  });

  it('formatDateTime falls back to the raw string for invalid input', () => {
    expect(formatDateTime('not-a-date')).toBe('not-a-date');
  });

  it('formatRelativeTime relative wording follows language', async () => {
    const threeDaysAgo = new Date(Date.now() - 3 * 86_400_000);
    await i18n.changeLanguage('zh-CN');
    expect(formatRelativeTime(threeDaysAgo)).toMatch(/3\s*天前/);
    await i18n.changeLanguage('en');
    expect(formatRelativeTime(threeDaysAgo)).toContain('3 days ago');
    await i18n.changeLanguage('zh-CN');
  });

  it('formatNumber groups thousands', () => {
    expect(formatNumber(12345)).toBe('12,345');
  });

  it('time is always 24-hour (no AM/PM even in en)', async () => {
    const evening = new Date('2026-05-12T20:30:00');
    await i18n.changeLanguage('en');
    expect(formatTime(evening)).toMatch(/^20:30/);
    expect(formatTime(evening)).not.toMatch(/PM/i);
    expect(formatDateTime(evening)).toContain('20:30');
    await i18n.changeLanguage('zh-CN');
    expect(formatTime(evening)).toMatch(/^20:30/);
  });
});

describe('utils/date (ISO-string façade)', () => {
  it('formatDateTime(null) renders as -', () => {
    expect(isoDateTime(null)).toBe('-');
    expect(isoDateTime(undefined)).toBe('-');
  });

  it('formatRelativeTime returns invalid input as-is', () => {
    expect(isoRelative('oops')).toBe('oops');
  });
});
