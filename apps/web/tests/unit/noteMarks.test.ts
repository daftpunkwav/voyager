/**
 * @file noteMarks
 * @description Unit tests for note highlight marks: parsing toned marks,
 * toolbar color toggle/recolor, range expansion and flattening, multi-line
 * painting, and clearing stray marks including inside code fences.
 */

import { describe, expect, it } from 'vitest';
import {
  applyNoteHighlight,
  applyNoteHighlightInDoc,
  expandHighlightRange,
  flattenMultilineMarks,
  notesHlMarkProps,
  parseHlTone,
  parseNoteHighlight,
  remarkNoteMarks,
  scanMarks,
  splitMarkedText,
  toggleNoteHighlight,
  wrapNoteHighlight,
} from '@/pages/notes/noteMarks';

describe('noteMarks', () => {
  it('parses toned marks and bare ==text==', () => {
    expect(parseNoteHighlight('==cool:中间件==')).toEqual({ tone: 'cool', inner: '中间件' });
    expect(parseNoteHighlight('==中间件==')).toEqual({ tone: 'warm', inner: '中间件' });
    expect(parseNoteHighlight('==violet:紫==')).toEqual({ tone: 'violet', inner: '紫' });
    expect(parseNoteHighlight('==rgb7c3aed:自定义==')).toEqual({
      tone: 'rgb7c3aed',
      inner: '自定义',
    });
    expect(parseNoteHighlight('普通')).toBeNull();
  });

  it('custom colors accept rgb / #hex; toggling the same color removes it', () => {
    expect(parseHlTone('#7C3AED')).toBe('rgb7c3aed');
    expect(wrapNoteHighlight('x', 'sand')).toBe('==sand:x==');
    expect(toggleNoteHighlight('词', 'rgb7c3aed')).toBe('==rgb7c3aed:词==');
    expect(toggleNoteHighlight('==rgb7c3aed:词==', 'rgb7c3aed')).toBe('词');
    expect(notesHlMarkProps('notes-hl-rgb notes-hl-rgb7c3aed')).toEqual({
      className: 'notes-hl-rgb notes-hl-rgb7c3aed',
      color: '#7c3aed',
    });
  });

  it('toggling the same toolbar color removes it; a different color rewrites it', () => {
    expect(toggleNoteHighlight('中间件', 'cool')).toBe('==cool:中间件==');
    expect(toggleNoteHighlight('==cool:中间件==', 'cool')).toBe('中间件');
    expect(toggleNoteHighlight('==cool:中间件==', 'rose')).toBe('==rose:中间件==');
    expect(applyNoteHighlight('==warm:中间件==', 'clear')).toBe('中间件');
    expect(wrapNoteHighlight('x', 'lime')).toBe('==lime:x==');
  });

  it('a selection exactly on inner expands to the whole mark', () => {
    const doc = '前==cool:中间件==后';
    const innerFrom = doc.indexOf('中间件');
    expect(expandHighlightRange(doc, innerFrom, innerFrom + 3)).toEqual({
      from: doc.indexOf('==cool:'),
      to: doc.indexOf('后'),
    });
  });

  it('multi-line text is painted per line, with list and heading prefixes kept outside the marks', () => {
    expect(applyNoteHighlight('第一段\n\n第二段', 'cool')).toBe(
      '==cool:第一段==\n\n==cool:第二段=='
    );
    expect(applyNoteHighlight('- aa\n- bb', 'rose')).toBe('- ==rose:aa==\n- ==rose:bb==');
    expect(applyNoteHighlight('## 标题\n正文', 'warm')).toBe('## ==warm:标题==\n==warm:正文==');
    expect(applyNoteHighlight('==cool:a==\n==cool:b==', 'cool')).toBe('a\nb');
  });

  it('a larger selection covering existing marks flattens then wraps, without nesting', () => {
    const doc = 'aaa==warm:bbb==ccc';
    const next = applyNoteHighlightInDoc(doc, 0, doc.length, 'cool');
    expect(next).toBe('==cool:aaabbbccc==');
    expect(next.includes('==warm:')).toBe(false);
    expect(scanMarks(next)).toHaveLength(1);
  });

  it('recoloring inside an existing mark splits it into three segments, no nesting', () => {
    const doc = '==warm:AAABBBCCC==';
    const from = doc.indexOf('BBB');
    const next = applyNoteHighlightInDoc(doc, from, from + 3, 'cool');
    expect(next).toBe('==warm:AAA====cool:BBB====warm:CCC==');
    expect(scanMarks(next).map((m) => next.slice(m.innerStart, m.innerEnd))).toEqual([
      'AAA',
      'BBB',
      'CCC',
    ]);
  });

  it('clearing removes an unclosed ==rose: prefix in the body', () => {
    const doc = '==rose:hello\nworld';
    expect(applyNoteHighlightInDoc(doc, 0, doc.length, 'clear')).toBe('hello\nworld');
  });

  it('clearing removes an unclosed ==rose: prefix inside a fence', () => {
    const doc = '```\n==rose:+-----+\n==rose:| box |\n==rose:+-----+\n```\n';
    const next = applyNoteHighlightInDoc(doc, 0, doc.length, 'clear');
    expect(next.includes('==rose:')).toBe(false);
    expect(next).toContain('+-----+');
    expect(next).toContain('| box |');
    expect(next).toContain('```');
  });

  it('clearing removes marks mistakenly written inside a fence', () => {
    const doc = '```\n==rose:| gateway |\n==\n```\n正文';
    const next = applyNoteHighlightInDoc(doc, 0, doc.length, 'clear');
    expect(next).toContain('| gateway |');
    expect(next.includes('==rose:')).toBe(false);
    expect(next.startsWith('```')).toBe(true);
  });

  it('no marks are written inside code fences', () => {
    const doc = '```\nhello\n```\n\nhello 正文';
    const from = doc.indexOf('hello');
    const next = applyNoteHighlightInDoc(doc, from, from + 5, 'warm');
    expect(next.startsWith('```\nhello\n```')).toBe(true);
    const body = doc.lastIndexOf('hello');
    const painted = applyNoteHighlightInDoc(doc, body, body + 5, 'warm');
    expect(painted).toContain('==warm:hello== 正文');
    expect(painted.startsWith('```\nhello\n```')).toBe(true);
  });

  it('a large selection containing bold is wrapped per line without nesting in source', () => {
    const doc = '1. **学习与了解** 说明\n2. 第二点';
    const next = applyNoteHighlight(doc, 'cool');
    expect(next).toBe('1. ==cool:**学习与了解** 说明==\n2. ==cool:第二点==');
    expect(scanMarks(next)).toHaveLength(2);
  });

  it('legacy cross-line marks are split into one mark per line before rendering', () => {
    expect(flattenMultilineMarks('前==cool:上\n\n下==后')).toBe('前==cool:上==\n\n==cool:下==后');
  });

  it('a four-backtick fence is not closed early by three backticks', () => {
    const doc = '````\nconst x = 1\n```\nstill code\n````\n正文';
    const from = doc.indexOf('still');
    const skipped = applyNoteHighlightInDoc(doc, from, from + 10, 'rose');
    expect(skipped).toContain('still code');
    expect(skipped.includes('==rose:still')).toBe(false);
    const body = doc.indexOf('正文');
    const painted = applyNoteHighlightInDoc(doc, body, body + 2, 'rose');
    expect(painted).toContain('==rose:正文==');
  });

  it('clearing does not delete literal ==a== inside code blocks', () => {
    const doc = '```\nconst pattern = "==a=="\n```\n';
    const next = applyNoteHighlightInDoc(doc, 0, doc.length, 'clear');
    expect(next).toContain('const pattern = "==a=="');
  });

  it('a selection over broken nested marks flattens then wraps', () => {
    const doc = '==cool:outer ==warm:inner== tail==';
    const next = applyNoteHighlightInDoc(doc, 0, doc.length, 'lime');
    expect(next.includes('==cool:')).toBe(false);
    expect(next.includes('==warm:')).toBe(false);
    expect(next.startsWith('==lime:')).toBe(true);
    expect(next.includes('inner')).toBe(true);
  });

  it('no marks are written inside inline code', () => {
    const doc = 'see `hello` please hello';
    const from = doc.indexOf('hello');
    const skipped = applyNoteHighlightInDoc(doc, from, from + 5, 'warm');
    expect(skipped).toContain('`hello`');
    expect(skipped.includes('==warm:hello==')).toBe(false);
    const body = doc.lastIndexOf('hello');
    const painted = applyNoteHighlightInDoc(doc, body, body + 5, 'warm');
    expect(painted).toContain('`hello` please ==warm:hello==');
  });

  it('a line containing inline code is wrapped whole, not split at the backticks', () => {
    const doc = '行内 `hello` 外面';
    expect(applyNoteHighlight(doc, 'cool')).toBe('==cool:行内 `hello` 外面==');
  });

  it('ASCII box lines and table rows are never painted, but text inside cells can be', () => {
    const box = '+-----+\n| box |\n+-----+';
    expect(applyNoteHighlight(box, 'rose')).toBe(box);
    const table = '| a | b |\n| - | - |\n| c | d |';
    expect(applyNoteHighlight(table, 'cool')).toBe(table);
    const cell = '| hello |';
    const from = cell.indexOf('hello');
    expect(applyNoteHighlightInDoc(cell, from, from + 5, 'lime')).toBe('| ==lime:hello== |');
  });

  it('splits out mark nodes without harming plain text outside code fences', () => {
    const nodes = splitMarkedText('见 ==cool:中间件== 与 ==暖==');
    expect(nodes.map((n) => n.type)).toEqual(['text', 'mark', 'text', 'mark']);
    expect(nodes[1].data?.hProperties).toEqual({ className: ['notes-hl-cool'] });
    expect((nodes[1].children as { value: string }[])[0].value).toBe('中间件');
    expect(nodes[3].data?.hProperties).toEqual({ className: ['notes-hl-warm'] });
  });

  it('preview wraps bold into the mark without leaking ==', () => {
    const tree = {
      type: 'root',
      children: [
        {
          type: 'paragraph',
          children: [
            { type: 'text', value: '==cool:' },
            { type: 'strong', children: [{ type: 'text', value: '学习与了解' }] },
            { type: 'text', value: ' 说明==' },
          ],
        },
      ],
    };
    remarkNoteMarks()(tree);
    const p = tree.children[0];
    expect(p.children.map((n) => n.type)).toEqual(['mark']);
    const mark = p.children[0];
    expect(mark.data?.hProperties).toEqual({ className: ['notes-hl-cool'] });
    expect(mark.children?.map((n) => n.type)).toEqual(['strong', 'text']);
    const texts = JSON.stringify(tree);
    expect(texts.includes('==')).toBe(false);
  });
});
