/**
 * @file utilsErrors
 * @description Pins the error-shape contract (utils/errors.ts): legacy
 * envelope detection, message extraction branches, and the unified
 * backend-unreachable copy.
 */

import { beforeAll, describe, expect, it } from 'vitest';
import { initI18n, i18n } from '@/i18n';
import { backendUnreachable, isApiError, extractErrorMessage } from '@/utils/errors';

beforeAll(() => {
  initI18n();
  void i18n.changeLanguage('zh-CN');
});

describe('utils/errors isApiError', () => {
  it('accepts the { error: { message } } envelope shape', () => {
    expect(isApiError({ error: { message: 'x' } })).toBe(true);
  });

  it('rejects other shapes', () => {
    expect(isApiError(null)).toBe(false);
    expect(isApiError('boom')).toBe(false);
    expect(isApiError({ error: 'boom' })).toBe(false);
    expect(isApiError({ error: { message: 42 } })).toBe(false);
    expect(isApiError(new Error('boom'))).toBe(false);
  });
});

describe('utils/errors extractErrorMessage', () => {
  it('returns the envelope message for API errors', () => {
    expect(extractErrorMessage({ error: { message: '服务出错' } })).toBe('服务出错');
  });

  it('maps fetch-flavored TypeErrors to the unreachable copy', () => {
    expect(extractErrorMessage(new TypeError('Failed to fetch'))).toBe(backendUnreachable());
    expect(extractErrorMessage(new TypeError('network down'))).toBe(backendUnreachable());
  });

  it('maps network-flavored Errors to the unreachable copy', () => {
    expect(extractErrorMessage(new Error('NetworkError'))).toBe(backendUnreachable());
    expect(extractErrorMessage(new Error('Load failed'))).toBe(backendUnreachable());
  });

  it('returns a plain Error message as-is', () => {
    expect(extractErrorMessage(new Error('validation failed'))).toBe('validation failed');
  });

  it('falls back to the unknown-retry copy for non-error values', () => {
    expect(extractErrorMessage(42)).toBe(i18n.t('errors:unknownRetry'));
    expect(extractErrorMessage(undefined)).toBe(i18n.t('errors:unknownRetry'));
  });
});

describe('utils/errors backendUnreachable', () => {
  it('resolves through the errors namespace and follows language', async () => {
    expect(backendUnreachable()).toBe(i18n.t('errors:backendUnreachable'));
    await i18n.changeLanguage('en');
    expect(backendUnreachable()).toBe(i18n.t('errors:backendUnreachable'));
    await i18n.changeLanguage('zh-CN');
  });
});
