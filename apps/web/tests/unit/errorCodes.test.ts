/**
 * @file errorCodes
 * @description Alignment contract between the errorCodes display mapping and
 * the backend ErrorSuffix (§7.10 unified error codes). Copy lives in the
 * errors namespace and follows UI language switches (describeError goes
 * through i18n.t).
 */

import { beforeAll, describe, expect, it } from 'vitest';
import { describeError, formatErrorToast, ERROR_CODES } from '@/utils/errorCodes';
import { initI18n, i18n } from '@/i18n';

// Mirrors the ErrorSuffix enum values in platform/contracts/platform_contracts/errors.py
const BACKEND_SUFFIXES = [
  'UNAVAILABLE',
  'QUEUE_FULL',
  'NOT_FOUND',
  'AUTH_REQUIRED',
  'FORBIDDEN',
  'RATE_LIMITED',
  'INVALID_INPUT',
  'CONFLICT',
  'INTERNAL',
];

beforeAll(() => {
  initI18n();
  void i18n.changeLanguage('zh-CN');
});

describe('utils/errorCodes (§7.10 error-code contract)', () => {
  it('registers all nine backend ErrorSuffix values', () => {
    for (const suffix of BACKEND_SUFFIXES) {
      expect(ERROR_CODES[suffix], `缺少后缀 ${suffix}`).toBeDefined();
    }
  });

  it('full codes <domain>.<suffix> match by suffix', () => {
    expect(describeError('GRAPH.UNAVAILABLE').title).toBe('服务暂不可用');
    expect(describeError('LLM.RATE_LIMITED').severity).toBe('warning');
  });

  it('bare suffixes (bridge-local codes) match directly', () => {
    expect(describeError('NOT_FOUND').title).toBe('资源不存在');
    expect(describeError('NOT_IMPLEMENTED').title).toBe('功能尚未迁移');
  });

  it('unknown codes fall into FALLBACK', () => {
    expect(describeError('WEIRD.NO_SUCH_CODE')).toEqual({
      title: '发生错误',
      hint: '请稍后重试或查看日志',
      severity: 'error',
    });
  });

  it('formatErrorToast uses the caller-provided fallback text for unknown codes', () => {
    expect(formatErrorToast('X.Y', '自定义说明')).toBe('[X.Y] 自定义说明');
    expect(formatErrorToast('GRAPH.NOT_FOUND')).toBe('[GRAPH.NOT_FOUND] 资源不存在');
  });

  it('error descriptions follow language switches (errors ns)', async () => {
    await i18n.changeLanguage('en');
    expect(describeError('GRAPH.UNAVAILABLE').title).toBe('Service unavailable');
    expect(describeError('WEIRD.NO_SUCH_CODE').title).toBe('Something went wrong');
    await i18n.changeLanguage('zh-CN');
    expect(describeError('GRAPH.UNAVAILABLE').title).toBe('服务暂不可用');
  });
});
