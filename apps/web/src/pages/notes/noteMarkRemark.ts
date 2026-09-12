/**
 * @file noteMarkRemark
 * @description remark plugin for the note preview that turns ==tone:text== into <mark> elements; not enabled for chat rendering.
 *
 * Responsibilities:
 * - Transform scanned highlight spans into mark nodes with per-tone
 *   classes (rgb tones carry the extra notes-hl-rgb class)
 * - Keep marks within a single text node (no cross-node marks)
 */

import { isRgbTone, type NoteHlTone } from './noteHl';
import { scanMarks } from './noteMarkScan';

const OBJECT_CHAR = '\uFFFC';

interface MdNode {
  type: string;
  value?: string;
  children?: MdNode[];
  data?: { hName?: string; hProperties?: Record<string, unknown> };
}

function markNode(tone: NoteHlTone, children: MdNode[]): MdNode {
  const className = isRgbTone(tone) ? ['notes-hl-rgb', `notes-hl-${tone}`] : [`notes-hl-${tone}`];
  return {
    type: 'mark',
    data: { hName: 'mark', hProperties: { className } },
    children,
  };
}

/** Splits ==tone:text== occurrences within a single line (no cross-node marks) into text/mark nodes; used by unit tests and as the degenerate path. */
export function splitMarkedText(value: string): MdNode[] {
  const marks = scanMarks(value);
  if (marks.length === 0) return [{ type: 'text', value }];
  const out: MdNode[] = [];
  let last = 0;
  for (const m of marks) {
    if (m.start > last) out.push({ type: 'text', value: value.slice(last, m.start) });
    out.push(markNode(m.tone, [{ type: 'text', value: value.slice(m.innerStart, m.innerEnd) }]));
    last = m.end;
  }
  if (last < value.length) out.push({ type: 'text', value: value.slice(last) });
  return out.length ? out : [{ type: 'text', value }];
}

function splitTextAt(value: string, locals: number[]): string[] {
  const pts = [...new Set(locals.filter((p) => p > 0 && p < value.length))].sort((a, b) => a - b);
  if (pts.length === 0) return [value];
  const parts: string[] = [];
  let prev = 0;
  for (const p of pts) {
    parts.push(value.slice(prev, p));
    prev = p;
  }
  parts.push(value.slice(prev));
  return parts.filter((p) => p.length > 0);
}

function wrapMarksInChildren(parent: MdNode): void {
  const children = parent.children;
  if (!children?.length) return;

  type Span = {
    kind: 'text' | 'atom';
    index: number;
    absStart: number;
    absEnd: number;
    value?: string;
  };
  const spans: Span[] = [];
  let abs = 0;
  for (let i = 0; i < children.length; i += 1) {
    const c = children[i];
    if (c.type === 'text' && typeof c.value === 'string') {
      spans.push({
        kind: 'text',
        index: i,
        absStart: abs,
        absEnd: abs + c.value.length,
        value: c.value,
      });
      abs += c.value.length;
    } else {
      spans.push({ kind: 'atom', index: i, absStart: abs, absEnd: abs + 1 });
      abs += 1;
    }
  }
  const concat = spans.map((s) => (s.kind === 'text' ? (s.value ?? '') : OBJECT_CHAR)).join('');
  const marks = scanMarks(concat);
  if (marks.length === 0) return;

  const cuts = new Map<number, number[]>();
  const addCut = (absPos: number) => {
    for (const s of spans) {
      if (s.kind !== 'text' || s.value == null) continue;
      if (absPos >= s.absStart && absPos <= s.absEnd) {
        const local = absPos - s.absStart;
        const arr = cuts.get(s.index) ?? [];
        arr.push(local);
        cuts.set(s.index, arr);
        return;
      }
    }
  };
  for (const m of marks) {
    addCut(m.start);
    addCut(m.innerStart);
    addCut(m.innerEnd);
    addCut(m.end);
  }

  const flat: MdNode[] = [];
  const flatAbs: { absStart: number; absEnd: number }[] = [];
  for (let i = 0; i < children.length; i += 1) {
    const c = children[i];
    const span = spans[i];
    if (c.type === 'text' && typeof c.value === 'string' && cuts.has(i)) {
      let local = 0;
      for (const part of splitTextAt(c.value, cuts.get(i) ?? [])) {
        flat.push({ type: 'text', value: part });
        flatAbs.push({
          absStart: span.absStart + local,
          absEnd: span.absStart + local + part.length,
        });
        local += part.length;
      }
    } else {
      flat.push(c);
      flatAbs.push({ absStart: span.absStart, absEnd: span.absEnd });
    }
  }

  const out: MdNode[] = [];
  let i = 0;
  while (i < flat.length) {
    const hit = marks.find(
      (m) => flatAbs[i].absStart === m.start && flatAbs[i].absEnd === m.innerStart
    );
    if (!hit) {
      out.push(flat[i]);
      i += 1;
      continue;
    }
    const inner: MdNode[] = [];
    let k = i + 1;
    while (k < flat.length && flatAbs[k].absStart < hit.innerEnd) {
      inner.push(flat[k]);
      k += 1;
    }
    if (inner.length) out.push(markNode(hit.tone, inner));
    i = k < flat.length && flatAbs[k].absStart === hit.innerEnd ? k + 1 : k;
  }
  parent.children = out;
}

function walk(node: MdNode): void {
  if (node.type === 'code' || node.type === 'inlineCode' || !node.children) return;
  for (const child of node.children) walk(child);
  wrapMarksInChildren(node);
}

/** remark plugin: only added to the plugin list used by the note preview; chat rendering does not enable it. */
export function remarkNoteMarks() {
  return (tree: MdNode) => {
    walk(tree);
  };
}

export const NOTE_PREVIEW_REMARK = [remarkNoteMarks];
