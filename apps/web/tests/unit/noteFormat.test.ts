/**
 * @file noteFormat
 * @description Unit tests for the note editor inline formatting helpers:
 * toggle/unwrap behavior for italic, bold, strikethrough, code, and link
 * across mixed selections.
 */

import { describe, expect, it } from 'vitest';
import {
  toggleFence,
  toggleInlineFormat,
  toggleInlineFormatInDoc,
  toggleLinePrefixBlock,
} from '@/pages/notes/noteFormat';

describe('toggleInlineFormat italic', () => {
  it('wraps plain text and unwraps the same span on the second toggle', () => {
    expect(toggleInlineFormat('widget', 'em')).toBe('*widget*');
    expect(toggleInlineFormat('*widget*', 'em')).toBe('widget');
  });

  it('when the selection spans italic and plain text, italicizes everything and restores on the next toggle', () => {
    expect(toggleInlineFormat('see *widget* now', 'em')).toBe('*see widget now*');
    expect(toggleInlineFormat('*see widget now*', 'em')).toBe('see widget now');
  });

  it('removes italics when selecting the inner text without the asterisks', () => {
    const doc = 'before*widget*after';
    const inner = doc.indexOf('widget');
    const { next } = toggleInlineFormatInDoc(doc, inner, inner + 6, 'em');
    expect(next).toBe('beforewidgetafter');
  });

  it('italic on bold text yields bold italic; toggling italic again removes only the italics', () => {
    expect(toggleInlineFormat('**bold**', 'em')).toBe('***bold***');
    expect(toggleInlineFormat('***bold***', 'em')).toBe('**bold**');
  });
});

describe('toggleInlineFormat bold', () => {
  it('wraps plain text and unwraps on the second toggle', () => {
    expect(toggleInlineFormat('title', 'strong')).toBe('**title**');
    expect(toggleInlineFormat('**title**', 'strong')).toBe('title');
  });

  it('when the selection spans bold and plain text, bolds everything and restores on the next toggle', () => {
    expect(toggleInlineFormat('see **title** now', 'strong')).toBe('**see title now**');
    expect(toggleInlineFormat('**see title now**', 'strong')).toBe('see title now');
  });

  it('removes bold when selecting the inner text', () => {
    const doc = 'before**title**after';
    const inner = doc.indexOf('title');
    const { next } = toggleInlineFormatInDoc(doc, inner, inner + 5, 'strong');
    expect(next).toBe('beforetitleafter');
  });

  it('toggling bold on bold italic leaves only italic', () => {
    expect(toggleInlineFormat('***bold***', 'strong')).toBe('*bold*');
  });
});

describe('toggleInlineFormat strike/code/link', () => {
  it('strikethrough toggle and superset handling', () => {
    expect(toggleInlineFormat('gone', 'strike')).toBe('~~gone~~');
    expect(toggleInlineFormat('~~gone~~', 'strike')).toBe('gone');
    expect(toggleInlineFormat('a ~~b~~ c', 'strike')).toBe('~~a b c~~');
  });

  it('inline code toggle and superset handling', () => {
    expect(toggleInlineFormat('x', 'code')).toBe('`x`');
    expect(toggleInlineFormat('`x`', 'code')).toBe('x');
    expect(toggleInlineFormat('a `b` c', 'code')).toBe('`a b c`');
  });

  it('link wrap and unwrap; the superset strips the existing link then wraps once', () => {
    expect(toggleInlineFormat('doc', 'link')).toBe('[doc](https://)');
    expect(toggleInlineFormat('[doc](https://)', 'link')).toBe('doc');
    expect(toggleInlineFormat('see [doc](https://x) page', 'link')).toBe(
      '[see doc page](https://)'
    );
  });
});

describe('toggleFence / line prefix block', () => {
  it('code fence toggles on and off', () => {
    expect(toggleFence('hello')).toBe('```\nhello\n```');
    expect(toggleFence('```\nhello\n```')).toBe('hello');
  });

  it('multi-line mixed list/plain lines get the prefix applied to all at once and removed from all on the next toggle', () => {
    expect(toggleLinePrefixBlock('- a\nb', '- ')).toBe('- a\n- b');
    expect(toggleLinePrefixBlock('- a\n- b', '- ')).toBe('a\nb');
  });

  it('headings/quotes are unified across the whole block the same way', () => {
    expect(toggleLinePrefixBlock('## a\nb', '## ')).toBe('## a\n## b');
    expect(toggleLinePrefixBlock('## a\n## b', '## ')).toBe('a\nb');
    expect(toggleLinePrefixBlock('> a\nb', '> ')).toBe('> a\n> b');
  });
});
