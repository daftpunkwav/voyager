/**
 * @file noteBlocks
 * @description Unit tests for splitMarkdownBlocks: empty documents, headings
 * as their own blocks, and fenced code/list blocks kept whole with start
 * lines recorded.
 */

import { describe, expect, it } from 'vitest';
import { splitMarkdownBlocks } from '@/pages/notes/noteBlocks';

describe('splitMarkdownBlocks', () => {
  it('returns no blocks for an empty document', () => {
    expect(splitMarkdownBlocks('')).toEqual([]);
    expect(splitMarkdownBlocks('   \n\n')).toEqual([]);
  });

  it('keeps headings as their own block with ## preserved in source', () => {
    const blocks = splitMarkdownBlocks('## Hello\n\nA paragraph');
    expect(blocks).toHaveLength(2);
    expect(blocks[0].source).toBe('## Hello');
    expect(blocks[0].startLine).toBe(1);
    expect(blocks[1].source).toBe('A paragraph');
    expect(blocks[1].startLine).toBe(3);
  });

  it('records the start line for fenced code', () => {
    const md = ['前言', '', '```js', 'const n = 1;', '```'].join('\n');
    const blocks = splitMarkdownBlocks(md);
    expect(blocks[1].startLine).toBe(3);
    expect(blocks[1].source).toContain('```js');
  });

  it('keeps fenced code and lists as whole blocks', () => {
    const md = ['```js', 'const n = 1;', '```', '', '- a', '- b'].join('\n');
    const blocks = splitMarkdownBlocks(md);
    expect(blocks).toHaveLength(2);
    expect(blocks[0].source).toContain('```js');
    expect(blocks[1].source).toBe('- a\n- b');
  });
});
