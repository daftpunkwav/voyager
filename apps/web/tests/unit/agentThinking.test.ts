/**
 * @file agentThinking
 * @description Pins the thinking-text classification contract
 * (utils/agentThinking.ts): status/scaffold detection, the
 * status-vs-substance partition, persistence filtering, and the
 * dispatch-notice merge rule.
 */

import { describe, expect, it } from 'vitest';
import {
  isStatusLine,
  partitionThinking,
  isStatusOnlyThinking,
  persistableThinking,
  isDispatchNoticeOnly,
  coalesceEmptyBodyWithThinking,
} from '@/utils/agentThinking';

describe('utils/agentThinking isStatusLine', () => {
  it('treats blank lines as status scaffolding', () => {
    expect(isStatusLine('')).toBe(true);
    expect(isStatusLine('   ')).toBe(true);
  });

  it('matches the legacy bracketed Chinese markers', () => {
    expect(isStatusLine('[状态] 开始')).toBe(true);
    expect(isStatusLine('[执行] x')).toBe(true);
    expect(isStatusLine('[规划完成]')).toBe(true);
    expect(isStatusLine('[中间推理]')).toBe(true);
  });

  it('matches the legacy intent-routing formats', () => {
    expect(isStatusLine('执行 · 调用工具')).toBe(true);
    expect(isStatusLine('意图识别: 建图谱')).toBe(true);
    // \b after a CJK char only fires before an ASCII word char
    expect(isStatusLine('意图路由react')).toBe(true);
    expect(isStatusLine('正在生成回答')).toBe(true);
  });

  it('matches round markers with and without mode banners', () => {
    // Bare `第 n/m 轮` misses: the legacy pattern ends in \b, which never
    // fires after a CJK char. Assert the shapes that do match.
    expect(isStatusLine('第 1/2 轮abc')).toBe(true);
    expect(isStatusLine('第 1/4 轮 · react')).toBe(true);
    expect(isStatusLine('推理中 第 2 / 4 轮')).toBe(true);
    expect(isStatusLine('推理中 (round 1/4 · plan_execute)')).toBe(true);
    expect(isStatusLine('第 1/4 轮')).toBe(false);
  });

  it('does not flag substantive reasoning', () => {
    expect(isStatusLine('我需要先检查一下图谱的当前状态。')).toBe(false);
    expect(isStatusLine('[中间推理] 这里有个关键线索')).toBe(false);
  });
});

describe('utils/agentThinking partitionThinking', () => {
  it('separates status lines from substantive text', () => {
    const { statusLines, realThinking } = partitionThinking(
      '[状态] 开始\n真正在思考的内容\n第 1/2 轮 · react\n'
    );
    expect(statusLines).toEqual(['[状态] 开始', '第 1/2 轮 · react']);
    expect(realThinking).toBe('真正在思考的内容');
  });

  it('strips the [中间推理] prefix but keeps the body as substance', () => {
    const { realThinking, statusLines } = partitionThinking('[中间推理]  body text');
    expect(realThinking).toBe('body text');
    expect(statusLines).toEqual([]);
  });

  it('keeps a bare [中间推理] marker as status', () => {
    const { statusLines, realThinking } = partitionThinking('[中间推理]');
    expect(statusLines).toEqual(['[中间推理]']);
    expect(realThinking).toBe('');
  });

  it('keeps blank separators between substance paragraphs', () => {
    const { realThinking } = partitionThinking('\n\nhello\n\nworld\n\n');
    expect(realThinking).toBe('hello\n\nworld');
  });
});

describe('utils/agentThinking persistence helpers', () => {
  it('isStatusOnlyThinking is true only when no substance remains', () => {
    expect(isStatusOnlyThinking('[状态] 开始\n第 1/2 轮 · react')).toBe(true);
    expect(isStatusOnlyThinking('[状态] 开始\n实质内容')).toBe(false);
  });

  it('persistableThinking drops scaffolding and null input', () => {
    expect(persistableThinking('[状态] 开始\n实质内容')).toBe('实质内容');
    expect(persistableThinking(null)).toBe('');
    expect(persistableThinking(undefined)).toBe('');
  });
});

describe('utils/agentThinking dispatch-notice merge', () => {
  it('detects short dispatch notices without headings', () => {
    expect(isDispatchNoticeOnly('先交由 **Iris** 处理资料检索。')).toBe(true);
    expect(isDispatchNoticeOnly('交由 Atlas 建图谱')).toBe(true);
  });

  it('rejects non-notices: empty, long, or headed bodies', () => {
    expect(isDispatchNoticeOnly('')).toBe(false);
    expect(isDispatchNoticeOnly('a'.repeat(281))).toBe(false);
    expect(isDispatchNoticeOnly('先交由 X 处理\n## 小节标题')).toBe(false);
    expect(isDispatchNoticeOnly('我来直接处理这件事。')).toBe(false);
  });

  it('coalesceEmptyBodyWithThinking merges only when body is a notice and thinking is substantive', () => {
    const notice = '先交由 Iris 处理。';
    const thinking = 'x'.repeat(80);
    expect(coalesceEmptyBodyWithThinking(notice, thinking)).toEqual({
      content: `${notice}\n\n${thinking}`,
      thinking: '',
    });
  });

  it('coalesceEmptyBodyWithThinking leaves ordinary pairs untouched', () => {
    expect(coalesceEmptyBodyWithThinking('普通正文', '短思考')).toEqual({
      content: '普通正文',
      thinking: '短思考',
    });
    expect(coalesceEmptyBodyWithThinking(noticeBody(), 'short')).toEqual({
      content: noticeBody(),
      thinking: 'short',
    });

    function noticeBody() {
      return '先交由 Iris 处理。';
    }
  });
});
