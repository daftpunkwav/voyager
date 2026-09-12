/**
 * @file pageMeta
 * @description Unit tests for resolvePageTitle: section names shared with
 * sidebar nav labels, no fabricated titles for unknown paths, and titles
 * following UI language changes.
 */

import { beforeAll, describe, expect, it } from 'vitest';
import { resolvePageTitle } from '@/shell/pageMeta';
import { initI18n, i18n } from '@/i18n';

beforeAll(() => {
  initI18n();
  void i18n.changeLanguage('zh-CN');
});

describe('resolvePageTitle', () => {
  it('returns the section name for both top-level and detail pages (same source as sidebar nav labels)', () => {
    expect(resolvePageTitle('/')).toBe('对话');
    expect(resolvePageTitle('/chat/abc')).toBe('对话');
    expect(resolvePageTitle('/team')).toBe('团队');
    expect(resolvePageTitle('/notes')).toBe('笔记');
    expect(resolvePageTitle('/sources')).toBe('资源库');
    expect(resolvePageTitle('/sources/repo/x')).toBe('资源库');
    expect(resolvePageTitle('/graph')).toBe('图谱');
    expect(resolvePageTitle('/code-graph/x')).toBe('图谱');
    expect(resolvePageTitle('/overview')).toBe('总览');
    expect(resolvePageTitle('/activity')).toBe('活动');
    expect(resolvePageTitle('/system/health')).toBe('服务状态');
    expect(resolvePageTitle('/usage')).toBe('用量');
    expect(resolvePageTitle('/settings')).toBe('设置');
  });

  it('does not fabricate a title for unknown paths', () => {
    expect(resolvePageTitle('/no-such')).toBe('');
  });

  it('title follows UI language changes (shell:nav.*)', async () => {
    await i18n.changeLanguage('en');
    expect(resolvePageTitle('/')).toBe('Chat');
    expect(resolvePageTitle('/settings')).toBe('Settings');
    await i18n.changeLanguage('zh-CN');
    expect(resolvePageTitle('/')).toBe('对话');
  });
});
