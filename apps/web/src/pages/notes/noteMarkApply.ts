/**
 * @file noteMarkApply
 * @description Applies or clears highlight marks over a document selection; code fences stay untouched and nested == is not allowed.
 *
 * Responsibilities:
 * - Apply/clear highlight tones over selections with fence, inline-code,
 *   structural-line, and block-prefix protection
 * - Flatten existing toned markup before re-wrapping (no nested ==)
 * - Compute the minimal document replacement for a single dispatch
 */

import {
  NOTE_HL_KIND,
  parseNoteHighlight,
  wrapNoteHighlight,
  type NoteHlAction,
  type NoteHlTone,
} from './noteHl';
import {
  fenceRanges,
  findMarks,
  inlineCodeRanges,
  parseFenceLine,
  scanMarks,
  splitBlockPrefix,
  type NoteMarkSpan,
} from './noteMarkScan';

interface TextSpan {
  kind: 'text' | 'fence';
  start: number;
  end: number;
  tone: NoteHlTone | null;
}

function flattenTonedMarkup(text: string): string {
  let s = text;
  for (let n = 0; n < 32; n += 1) {
    const marks = scanMarks(s, true);
    if (marks.length === 0) break;
    for (const m of [...marks].reverse()) {
      s = s.slice(0, m.start) + s.slice(m.innerStart, m.innerEnd) + s.slice(m.end);
    }
  }
  s = s.replace(new RegExp(`==(${NOTE_HL_KIND}):`, 'gi'), '');
  return s.replace(/(^|[^=])==(?!=)/g, '$1');
}

/** Pipe tables / ASCII box-drawing lines: wrapping a whole line in == breaks their structure, and preview would leak syntax or misparse them as tables. */
function isStructuralLine(line: string): boolean {
  const t = line.trim();
  if (!t) return false;
  if (/^[+┌├└┬┴][-─=━]{2,}/.test(t)) return true;
  if (/^[+=\-─━]{4,}$/.test(t)) return true;
  if (/^[|│]/.test(t)) return true;
  return false;
}

function wrapHighlightLine(line: string, tone: NoteHlTone): string {
  if (parseFenceLine(line) || isStructuralLine(line)) return line;
  const { prefix, rest } = splitBlockPrefix(line);
  if (isStructuralLine(rest)) return line;
  const body = flattenTonedMarkup(rest);
  if (!body.trim()) return prefix + body;
  const parsed = parseNoteHighlight(body);
  if (parsed) {
    if (parsed.tone === tone) return prefix + body;
    if (!parsed.inner.includes('==')) return prefix + wrapNoteHighlight(parsed.inner, tone);
  }
  if (body.includes('==')) return prefix + body;
  return prefix + wrapNoteHighlight(body, tone);
}

function buildSpans(doc: string): TextSpan[] {
  const fences = fenceRanges(doc);
  const marks = findMarks(doc);
  const spans: TextSpan[] = [];
  const n = doc.length;
  let pos = 0;
  let fi = 0;
  let mi = 0;
  while (pos < n) {
    const fence = fi < fences.length && fences[fi].start === pos ? fences[fi] : null;
    if (fence) {
      spans.push({ kind: 'fence', start: fence.start, end: fence.end, tone: null });
      pos = fence.end;
      fi += 1;
      continue;
    }
    const mark = mi < marks.length && marks[mi].start === pos ? marks[mi] : null;
    if (mark) {
      spans.push({ kind: 'text', start: mark.innerStart, end: mark.innerEnd, tone: mark.tone });
      pos = mark.end;
      mi += 1;
      continue;
    }
    let next = n;
    if (fi < fences.length) next = Math.min(next, fences[fi].start);
    if (mi < marks.length) next = Math.min(next, marks[mi].start);
    spans.push({ kind: 'text', start: pos, end: next, tone: null });
    pos = next;
  }
  return spans.filter((s) => s.end > s.start);
}

function splitSpans(spans: TextSpan[], points: number[]): TextSpan[] {
  const cuts = [...new Set(points)].sort((a, b) => a - b);
  const out: TextSpan[] = [];
  for (const s of spans) {
    if (s.kind === 'fence') {
      out.push(s);
      continue;
    }
    const inner = cuts.filter((p) => p > s.start && p < s.end);
    let a = s.start;
    for (const p of inner) {
      out.push({ kind: 'text', start: a, end: p, tone: s.tone });
      a = p;
    }
    out.push({ kind: 'text', start: a, end: s.end, tone: s.tone });
  }
  return out.filter((s) => s.end > s.start);
}

function emitSpans(
  doc: string,
  spans: TextSpan[],
  clearRange?: { from: number; to: number }
): string {
  type Group =
    | { kind: 'fence'; span: TextSpan }
    | { kind: 'text'; tone: NoteHlTone | null; chunks: TextSpan[] };
  const groups: Group[] = [];
  for (const s of spans) {
    if (s.kind === 'fence') {
      groups.push({ kind: 'fence', span: s });
      continue;
    }
    const last = groups[groups.length - 1];
    if (last && last.kind === 'text' && last.tone === s.tone) {
      last.chunks.push(s);
    } else {
      groups.push({ kind: 'text', tone: s.tone, chunks: [s] });
    }
  }
  return groups
    .map((g) => {
      if (g.kind === 'fence') {
        const raw = doc.slice(g.span.start, g.span.end);
        if (clearRange && g.span.end > clearRange.from && g.span.start < clearRange.to) {
          return stripAllMarks(raw);
        }
        return raw;
      }
      const text = g.chunks.map((c) => doc.slice(c.start, c.end)).join('');
      if (!g.tone) {
        if (
          clearRange &&
          g.chunks.some((c) => c.end > clearRange.from && c.start < clearRange.to)
        ) {
          return stripAllMarks(text);
        }
        return text;
      }
      return text
        .split('\n')
        .map((line) => wrapHighlightLine(line, g.tone as NoteHlTone))
        .join('\n');
    })
    .join('');
}

function hasWrappable(doc: string, s: TextSpan): boolean {
  if (s.kind !== 'text' || s.end <= s.start) return false;
  return doc
    .slice(s.start, s.end)
    .split('\n')
    .some((line) => splitBlockPrefix(line).rest.trim().length > 0 && !line.includes('=='));
}

function unwrapMark(doc: string, m: NoteMarkSpan): string {
  return doc.slice(0, m.start) + doc.slice(m.innerStart, m.innerEnd) + doc.slice(m.end);
}

function wrapInner(inner: string, tone: NoteHlTone): string {
  return inner
    .split('\n')
    .map((line) => wrapHighlightLine(line, tone))
    .join('\n');
}

function stripAllMarks(text: string): string {
  let s = text;
  for (let n = 0; n < 32; n += 1) {
    const marks = scanMarks(s, true);
    if (marks.length === 0) break;
    for (const m of [...marks].reverse()) {
      s = s.slice(0, m.start) + s.slice(m.innerStart, m.innerEnd) + s.slice(m.end);
    }
  }
  return s.replace(new RegExp(`==(${NOTE_HL_KIND}):`, 'gi'), '');
}

function intervalTransform(doc: string, from: number, to: number, action: NoteHlAction): string {
  const spans = splitSpans(buildSpans(doc), [from, to]);
  const inside = spans.filter((s) => s.kind === 'text' && s.start >= from && s.end <= to);
  const already =
    action !== 'clear' &&
    inside.some((s) => hasWrappable(doc, s)) &&
    inside.every((s) => !hasWrappable(doc, s) || s.tone === action);
  for (const s of spans) {
    if (s.kind === 'fence') continue;
    if (s.start >= from && s.end <= to) {
      if (action === 'clear' || already) s.tone = null;
      else s.tone = action;
    }
  }
  return emitSpans(doc, spans, action === 'clear' ? { from, to } : undefined);
}

/** Applies or clears a tone over [from, to) in the full document; fences stay untouched; an existing mark covering the range is flattened before re-wrapping. */
export function applyNoteHighlightInDoc(
  doc: string,
  from: number,
  to: number,
  action: NoteHlAction
): string {
  const text = doc.replace(/\r\n/g, '\n');
  let a = Math.max(0, Math.min(from, to));
  let b = Math.min(text.length, Math.max(from, to));
  if (a === b) return text;
  const inlines = inlineCodeRanges(text, fenceRanges(text));
  if (inlines.some((r) => r.start <= a && b <= r.end)) return text;
  const marks = findMarks(text);
  const containers = marks.filter((m) => m.start <= a && b <= m.end);
  if (containers.length === 1) {
    const m = containers[0];
    const inInner = m.innerStart <= a && b <= m.innerEnd;
    const proper = a > m.innerStart || b < m.innerEnd;
    if (inInner && proper && action !== 'clear' && action !== m.tone) {
      const left = text.slice(m.innerStart, a);
      const mid = text.slice(a, b);
      const right = text.slice(b, m.innerEnd);
      const pieces = [
        left ? wrapInner(left, m.tone) : '',
        wrapInner(mid, action),
        right ? wrapInner(right, m.tone) : '',
      ];
      return text.slice(0, m.start) + pieces.join('') + text.slice(m.end);
    }
    if (action === 'clear' || action === m.tone) {
      return unwrapMark(text, m);
    }
    return (
      text.slice(0, m.start) +
      wrapInner(text.slice(m.innerStart, m.innerEnd), action) +
      text.slice(m.end)
    );
  }
  return intervalTransform(text, a, b, action);
}

/** Treats a standalone text slice as the whole document (toolbar slices / flatten still work). */
export function applyNoteHighlight(selected: string, action: NoteHlAction): string {
  const text = selected.replace(/\r\n/g, '\n');
  return applyNoteHighlightInDoc(text, 0, text.length, action);
}

export function toggleNoteHighlight(selected: string, tone: NoteHlTone): string {
  return applyNoteHighlight(selected, tone);
}

/** Expands a selection that exactly matches a mark's inner text to the full mark, so clicking again with the same tone removes it. */
export function expandHighlightRange(
  doc: string,
  from: number,
  to: number
): { from: number; to: number } {
  const selected = doc.slice(from, to);
  if (parseNoteHighlight(selected)) return { from, to };
  const marks = findMarks(doc);
  const hit = marks.find((m) => m.innerStart === from && m.innerEnd === to);
  return hit ? { from: hit.start, to: hit.end } : { from, to };
}

function wrapInnerLines(inner: string, tone: NoteHlTone): string {
  return inner
    .split('\n')
    .map((line) => wrapHighlightLine(line, tone))
    .join('\n');
}

/** Splits multi-line marks into per-line ==tone:...== so remark can wrap a mark within a single paragraph phrasing. */
export function flattenMultilineMarks(md: string): string {
  let out = md.replace(/\r\n/g, '\n');
  const marks = findMarks(out);
  for (const m of [...marks].reverse()) {
    const inner = out.slice(m.innerStart, m.innerEnd);
    if (!inner.includes('\n')) continue;
    out = out.slice(0, m.start) + wrapInnerLines(inner, m.tone) + out.slice(m.end);
  }
  return out;
}
