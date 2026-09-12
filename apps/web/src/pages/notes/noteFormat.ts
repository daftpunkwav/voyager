/**
 * @file noteFormat
 * @description Inline and line-start Markdown format toggles shared by the toolbar (bold, italic, strike, inline code, link, headings, quotes, lists).
 *
 * Toggling a whole multi-line selection removes the prefix when every line
 * already has it, otherwise applies it uniformly. A "superset" selection (some
 * parts already formatted, some not) is flattened first and then wrapped.
 * Highlight formatting shares the same interaction model.
 *
 * Responsibilities:
 * - Toggle inline formats (bold, italic, strike, code, link) over plain
 *   selections and document ranges, flattening superset selections first
 * - Toggle line-start prefixes (headings, quotes, lists) and fences per
 *   line, removing old prefixes before applying new ones
 */

import { applyLinePrefix } from './noteLine';

export type InlineFormat = 'em' | 'strong' | 'strike' | 'code' | 'link';

export function toggleInlineFormat(text: string, kind: InlineFormat): string {
  if (!text.includes('\n')) return toggleInlineOne(text, kind);
  const lines = text.split('\n');
  const work = lines.filter((l) => l.trim() !== '');
  if (work.length === 0) return text;
  const allOn = work.every((l) => isWrapped(l, kind));
  return lines
    .map((l) => {
      if (l.trim() === '') return l;
      return allOn ? unwrap(l, kind) : wrap(flatten(l, kind), kind);
    })
    .join('\n');
}

/** Toggles the format over [from, to) in the full document; a selection inside a marker's inner text (delimiters excluded) is first expanded to the whole marked span. */
export function toggleInlineFormatInDoc(
  doc: string,
  from: number,
  to: number,
  kind: InlineFormat
): { from: number; to: number; next: string } {
  let a = Math.max(0, Math.min(from, to));
  let b = Math.min(doc.length, Math.max(from, to));
  if (a === b) {
    const { left, right } = markers(kind);
    const insert = left + right;
    return { from: a, to: b, next: doc.slice(0, a) + insert + doc.slice(b) };
  }
  if (!isWrapped(doc.slice(a, b), kind)) {
    const exp = expandWrap(doc, a, b, kind);
    if (exp && isWrapped(doc.slice(exp.from, exp.to), kind)) {
      a = exp.from;
      b = exp.to;
    }
  }
  const replaced = toggleInlineFormat(doc.slice(a, b), kind);
  return { from: a, to: b, next: doc.slice(0, a) + replaced + doc.slice(b) };
}

export function emptyInlineInsert(kind: InlineFormat): { insert: string; cursor: number } {
  const { left, right } = markers(kind);
  return { insert: left + right, cursor: left.length };
}

export function toggleFence(text: string): string {
  const trimmed = text.replace(/^\n+/, '').replace(/\n+$/, '');
  const fenced = /^```[^\n]*\n([\s\S]*?)\n```$/.exec(trimmed);
  if (fenced) return fenced[1];
  const inner = text.replace(/^\n/, '').replace(/\n$/, '');
  return `\`\`\`\n${inner}\n\`\`\``;
}

export function toggleFenceInDoc(
  doc: string,
  from: number,
  to: number
): { from: number; to: number; next: string } {
  let a = Math.max(0, Math.min(from, to));
  let b = Math.min(doc.length, Math.max(from, to));
  if (a === b) {
    const insert = '```\n\n```';
    return { from: a, to: b, next: doc.slice(0, a) + insert + doc.slice(b) };
  }
  const slice = doc.slice(a, b);
  const replaced = toggleFence(slice);
  return { from: a, to: b, next: doc.slice(0, a) + replaced + doc.slice(b) };
}

export function hasLinePrefix(text: string, prefix: string): boolean {
  const isTask = /^[-*]\s\[[ xX]\]\s/.test(text);
  if (prefix === '- ' && isTask) return false;
  return text.startsWith(prefix);
}

/** Multi-line selection: strip the prefix when every non-empty line already has it; otherwise apply it uniformly (lines that have it are kept). */
export function toggleLinePrefixBlock(text: string, prefix: string): string {
  const lines = text.split('\n');
  const work = lines.filter((l) => l.trim() !== '');
  if (work.length === 0) return text;
  const allOn = work.every((l) => hasLinePrefix(l, prefix));
  return lines
    .map((l) => {
      if (l.trim() === '') return l;
      if (allOn) return hasLinePrefix(l, prefix) ? l.slice(prefix.length) : l;
      if (hasLinePrefix(l, prefix)) return l;
      return applyLinePrefix(l, prefix);
    })
    .join('\n');
}

function markers(kind: InlineFormat): { left: string; right: string } {
  if (kind === 'em') return { left: '*', right: '*' };
  if (kind === 'strong') return { left: '**', right: '**' };
  if (kind === 'strike') return { left: '~~', right: '~~' };
  if (kind === 'code') return { left: '`', right: '`' };
  return { left: '[', right: '](https://)' };
}

function toggleInlineOne(text: string, kind: InlineFormat): string {
  if (isWrapped(text, kind)) return unwrap(text, kind);
  return wrap(flatten(text, kind), kind);
}

function isWrapped(text: string, kind: InlineFormat): boolean {
  if (kind === 'em') return isEmWrap(text);
  if (kind === 'strong') return isStrongWrap(text);
  if (kind === 'strike') return text.startsWith('~~') && text.endsWith('~~') && text.length >= 5;
  if (kind === 'code')
    return (
      text.startsWith('`') && text.endsWith('`') && text.length >= 3 && !text.startsWith('```')
    );
  return /^\[[^\]]*\]\([^)]*\)$/.test(text);
}

function isEmWrap(text: string): boolean {
  if (text.length < 3 || !(text.startsWith('*') && text.endsWith('*'))) return false;
  if (text.startsWith('**') && text.endsWith('**') && !text.startsWith('***')) return false;
  return true;
}

function isStrongWrap(text: string): boolean {
  return text.startsWith('**') && text.endsWith('**') && text.length >= 5;
}

function unwrap(text: string, kind: InlineFormat): string {
  if (kind === 'em') return text.slice(1, -1);
  if (kind === 'strong') return text.slice(2, -2);
  if (kind === 'strike') return text.slice(2, -2);
  if (kind === 'code') return text.slice(1, -1);
  const m = /^\[([^\]]*)\]\([^)]*\)$/.exec(text);
  return m ? m[1] : text;
}

function wrap(text: string, kind: InlineFormat): string {
  if (kind === 'em') return `*${text}*`;
  if (kind === 'strong') return `**${text}**`;
  if (kind === 'strike') return `~~${text}~~`;
  if (kind === 'code') return `\`${text}\``;
  return `[${text}](https://)`;
}

function flatten(text: string, kind: InlineFormat): string {
  if (kind === 'em') return flattenEm(text);
  if (kind === 'strong') return flattenStrong(text);
  if (kind === 'strike') return text.replace(/~~([\s\S]*?)~~/g, '$1');
  if (kind === 'code') return text.replace(/`([^`]+)`/g, '$1');
  return text.replace(/\[([^\]]*)\]\([^)]*\)/g, '$1');
}

function flattenEm(s: string): string {
  let i = 0;
  let out = '';
  while (i < s.length) {
    if (s.startsWith('**', i)) {
      const close = s.indexOf('**', i + 2);
      if (close >= 0) {
        out += `**${flattenEm(s.slice(i + 2, close))}**`;
        i = close + 2;
        continue;
      }
    }
    if (s[i] === '*') {
      const close = findEmClose(s, i + 1);
      if (close >= 0) {
        out += flattenEm(s.slice(i + 1, close));
        i = close + 1;
        continue;
      }
    }
    out += s[i];
    i += 1;
  }
  return out;
}

function findEmClose(s: string, from: number): number {
  let i = from;
  while (i < s.length) {
    if (s.startsWith('**', i)) {
      const c = s.indexOf('**', i + 2);
      if (c < 0) return -1;
      i = c + 2;
      continue;
    }
    if (s[i] === '*') return i;
    i += 1;
  }
  return -1;
}

function flattenStrong(s: string): string {
  let i = 0;
  let out = '';
  while (i < s.length) {
    if (s.startsWith('**', i)) {
      const close = s.indexOf('**', i + 2);
      if (close >= 0) {
        out += s.slice(i + 2, close);
        i = close + 2;
        continue;
      }
    }
    out += s[i];
    i += 1;
  }
  return out;
}

function runOf(doc: string, start: number, dir: -1 | 1, ch: string): number {
  let n = 0;
  let i = dir === -1 ? start - 1 : start;
  while (i >= 0 && i < doc.length && doc[i] === ch) {
    n += 1;
    i += dir;
  }
  return n;
}

function expandWrap(
  doc: string,
  from: number,
  to: number,
  kind: InlineFormat
): { from: number; to: number } | null {
  if (kind === 'em') {
    const before = runOf(doc, from, -1, '*');
    const after = runOf(doc, to, 1, '*');
    const n = Math.min(before, after);
    if (n >= 1 && n % 2 === 1) return { from: from - 1, to: to + 1 };
    return null;
  }
  if (kind === 'strong') {
    const before = runOf(doc, from, -1, '*');
    const after = runOf(doc, to, 1, '*');
    if (before >= 2 && after >= 2) return { from: from - 2, to: to + 2 };
    return null;
  }
  if (kind === 'strike') {
    const before = runOf(doc, from, -1, '~');
    const after = runOf(doc, to, 1, '~');
    if (before >= 2 && after >= 2) return { from: from - 2, to: to + 2 };
    return null;
  }
  if (kind === 'code') {
    const before = runOf(doc, from, -1, '`');
    const after = runOf(doc, to, 1, '`');
    if (before === 1 && after === 1) return { from: from - 1, to: to + 1 };
    return null;
  }
  if (from === 0 || doc[from - 1] !== '[') return null;
  const m = /^\]\([^)]*\)/.exec(doc.slice(to));
  if (!m) return null;
  return { from: from - 1, to: to + m[0].length };
}
