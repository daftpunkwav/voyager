/**
 * @file noteMarkScan
 * @description Scans note content for ==tone:...== marks; code fences and inline code are treated as literals.
 *
 * Responsibilities:
 * - Scan text for toned and legacy bare ==...== spans, returning exact
 *   boundaries and tones
 * - Classify fence lines and block prefixes so scanners can skip
 *   protected regions
 */

import { readToneAt, type NoteHlTone } from './noteHl';

export const FENCE_OPEN = /^( {0,3})(`{3,}|~{3,})(.*)$/;
export const BLOCK_PREFIX =
  /^(#{1,6}[ \t]+|(?:>[ \t]*)+|\s*[-*+][ \t]+\[[ xX]\][ \t]+|\s*[-*+][ \t]+|\s*\d+[.)][ \t]+)/;

export interface NoteMarkSpan {
  start: number;
  innerStart: number;
  innerEnd: number;
  end: number;
  tone: NoteHlTone;
}

export function parseFenceLine(
  line: string
): { char: string; length: number; rest: string } | null {
  const m = FENCE_OPEN.exec(line);
  if (!m) return null;
  return { char: m[2][0], length: m[2].length, rest: m[3] };
}

export function splitBlockPrefix(line: string): { prefix: string; rest: string } {
  if (parseFenceLine(line)) return { prefix: line, rest: '' };
  const m = BLOCK_PREFIX.exec(line);
  if (!m) return { prefix: '', rest: line };
  return { prefix: m[0], rest: line.slice(m[0].length) };
}

/** Scans for ==tone:...==; with tonedOnly=false it also recognizes bare ==...== (legacy notes). */
export function scanMarks(text: string, tonedOnly = false): NoteMarkSpan[] {
  const out: NoteMarkSpan[] = [];
  let i = 0;
  const n = text.length;
  while (i < n - 1) {
    if (text[i] !== '=' || text[i + 1] !== '=') {
      i += 1;
      continue;
    }
    let tone: NoteHlTone = 'warm';
    let innerStart = i + 2;
    let toned = false;
    const hit = readToneAt(text, i + 2);
    if (hit) {
      tone = hit.tone;
      innerStart = hit.innerStart;
      toned = true;
    }
    if (tonedOnly && !toned) {
      i += 1;
      continue;
    }
    const close = text.indexOf('==', innerStart);
    if (close < 0) {
      i += 1;
      continue;
    }
    if (close === innerStart) {
      i = close;
      continue;
    }
    out.push({ start: i, innerStart, innerEnd: close, end: close + 2, tone });
    i = close + 2;
  }
  return out;
}

function inRanges(ranges: { start: number; end: number }[], idx: number): boolean {
  return ranges.some((r) => idx >= r.start && idx < r.end);
}

/** CommonMark inline code: single or multi-backtick runs, never spanning fences; an unclosed opener is not treated as a protected range. */
export function inlineCodeRanges(
  content: string,
  fences: { start: number; end: number }[]
): { start: number; end: number }[] {
  const ranges: { start: number; end: number }[] = [];
  const n = content.length;
  let i = 0;
  while (i < n) {
    if (inRanges(fences, i) || content[i] !== '`') {
      i += 1;
      continue;
    }
    let run = 1;
    while (i + run < n && content[i + run] === '`') run += 1;
    let j = i + run;
    let found = false;
    while (j < n) {
      if (inRanges(fences, j)) break;
      if (content[j] === '`') {
        let m = 1;
        while (j + m < n && content[j + m] === '`') m += 1;
        if (m === run) {
          ranges.push({ start: i, end: j + m });
          i = j + m;
          found = true;
          break;
        }
        j += m;
        continue;
      }
      j += 1;
    }
    if (!found) i += run;
  }
  return ranges;
}

export function fenceRanges(content: string): { start: number; end: number }[] {
  const ranges: { start: number; end: number }[] = [];
  const n = content.length;
  let pos = 0;
  let inFence = false;
  let start = 0;
  let marker = '';
  let minLen = 0;
  while (pos <= n) {
    const nl = content.indexOf('\n', pos);
    const lineEnd = nl < 0 ? n : nl;
    const parsed = parseFenceLine(content.slice(pos, lineEnd));
    if (parsed) {
      if (!inFence) {
        inFence = true;
        marker = parsed.char;
        minLen = parsed.length;
        start = pos;
      } else if (parsed.char === marker && parsed.length >= minLen && parsed.rest.trim() === '') {
        ranges.push({ start, end: lineEnd });
        inFence = false;
      }
    }
    if (nl < 0) break;
    pos = nl + 1;
  }
  if (inFence) ranges.push({ start, end: n });
  return ranges;
}

export function protectedRanges(content: string): { start: number; end: number }[] {
  const fences = fenceRanges(content);
  return [...fences, ...inlineCodeRanges(content, fences)].sort((a, b) => a.start - b.start);
}

/** Highlight mark ranges in the body; == inside fences and inline code counts as literal text. */
export function findMarks(content: string): NoteMarkSpan[] {
  const fences = protectedRanges(content);
  if (fences.length === 0) return scanMarks(content, true);
  const out: NoteMarkSpan[] = [];
  let pos = 0;
  for (const f of fences) {
    if (f.start > pos) {
      for (const m of scanMarks(content.slice(pos, f.start), true)) {
        out.push({
          start: m.start + pos,
          innerStart: m.innerStart + pos,
          innerEnd: m.innerEnd + pos,
          end: m.end + pos,
          tone: m.tone,
        });
      }
    }
    pos = f.end;
  }
  if (pos < content.length) {
    for (const m of scanMarks(content.slice(pos), true)) {
      out.push({
        start: m.start + pos,
        innerStart: m.innerStart + pos,
        innerEnd: m.innerEnd + pos,
        end: m.end + pos,
        tone: m.tone,
      });
    }
  }
  return out;
}
