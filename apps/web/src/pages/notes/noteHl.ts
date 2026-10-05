/**
 * @file noteHl
 * @description Note highlight palette and markup syntax (`==tone:text==`); scanning and write algorithms live elsewhere.
 *
 * Responsibilities:
 * - Define the tone palette, label keys, and the `==tone:text==` markup
 *   grammar (built-in tones plus rgb hex tones)
 * - Parse, wrap, and validate highlight markup; map tones to preview
 *   mark props and recover stray markup inside code fences
 */

export const NOTE_HL_TONES = ['warm', 'cool', 'rose', 'lime', 'violet', 'sand'] as const;
export type NoteHlTone = (typeof NOTE_HL_TONES)[number] | `rgb${string}`;
export type NoteHlAction = NoteHlTone | 'clear';

/** Toolbar labels as flat i18n keys in the notes namespace; resolve with t(`notes:${key}`). */
export const NOTE_HL_LABEL: Record<(typeof NOTE_HL_TONES)[number], string> = {
  warm: 'hl.warm',
  cool: 'hl.cool',
  rose: 'hl.rose',
  lime: 'hl.lime',
  violet: 'hl.violet',
  sand: 'hl.sand',
};

/**
 * Marker names: built-in tones or rgb plus 6 hex digits (case-insensitive
 * when scanning; canonical form is lowercase).
 *
 * NOTE_HL_KIND is the single source of the tone alternation: every pattern
 * in this module is built from it, and the grammar test asserts each palette
 * tone is recognized. Global (/g) regexes carry lastIndex state, so the /g
 * patterns are factory functions returning a fresh object per call instead
 * of shared constants.
 */
export const NOTE_HL_KIND = 'warm|cool|rose|lime|violet|sand|rgb[0-9a-fA-F]{6}';
export const NOTES_HL_RGB_KEY = 'notes-hl-rgb';
export const NOTES_HL_RGB_DEFAULT = '7c3aed';

const RGB_TONE = /^rgb[0-9a-f]{6}$/;
const HEX6 = /^[0-9a-f]{6}$/;

/** `==tone:` prefix at any position; fresh /gi object per call. */
export function hlTonePrefixRegex(): RegExp {
  return new RegExp(`==(${NOTE_HL_KIND}):`, 'gi');
}

/** Full closed `==tone:text==` markup; fresh /gi object per call. */
export function hlToneClosedRegex(): RegExp {
  return new RegExp(`==(${NOTE_HL_KIND}):((?:(?!==).)+)==`, 'gi');
}

/** Tone prefix anchored at the string start; flagless and stateless. */
export const HL_TONE_AT = new RegExp(`^(${NOTE_HL_KIND}):`, 'i');

export function isRgbTone(tone: string): boolean {
  return RGB_TONE.test(tone);
}

/** Accepts warm / rgb7c3aed / #7c3aed / 7c3aed; returns null for invalid input. */
export function parseHlTone(raw: string): NoteHlTone | null {
  const t = raw.trim().toLowerCase();
  if ((NOTE_HL_TONES as readonly string[]).includes(t)) return t as (typeof NOTE_HL_TONES)[number];
  if (RGB_TONE.test(t)) return t as NoteHlTone;
  const hex = t.startsWith('#') ? t.slice(1) : t;
  if (HEX6.test(hex)) return `rgb${hex}` as NoteHlTone;
  return null;
}

export function rgbToneHex(tone: string): string | null {
  if (!isRgbTone(tone)) return null;
  return `#${tone.slice(3)}`;
}

export function readToneAt(
  text: string,
  innerFrom: number
): { tone: NoteHlTone; innerStart: number } | null {
  const m = HL_TONE_AT.exec(text.slice(innerFrom));
  if (!m || m.index !== 0) return null;
  return { tone: m[1].toLowerCase() as NoteHlTone, innerStart: innerFrom + m[0].length };
}

export function parseNoteHighlight(text: string): { tone: NoteHlTone; inner: string } | null {
  if (!text) return null;
  if (!(text.startsWith('==') && text.endsWith('==') && text.length >= 4)) return null;
  const body = text.slice(2, -2);
  if (body.includes('==')) return null;
  const m = HL_TONE_AT.exec(body);
  if (m && m.index === 0) {
    return { tone: m[1].toLowerCase() as NoteHlTone, inner: body.slice(m[0].length) };
  }
  return { tone: 'warm', inner: body };
}

export function wrapNoteHighlight(inner: string, tone: NoteHlTone): string {
  return `==${tone}:${inner}==`;
}

/** The preview sanitizer only allows known notes-hl-* classes; custom colors carry an inline --notes-hl custom property. */
export function notesHlMarkProps(raw: unknown): { className: string; color?: string } {
  const text = Array.isArray(raw) ? raw.join(' ') : String(raw ?? '');
  const named = /\bnotes-hl-(warm|cool|rose|lime|violet|sand)\b/.exec(text);
  if (named) return { className: `notes-hl-${named[1]}` };
  const rgb = /\bnotes-hl-(rgb[0-9a-f]{6})\b/i.exec(text);
  if (rgb) {
    const token = rgb[1].toLowerCase();
    return { className: `notes-hl-rgb notes-hl-${token}`, color: `#${token.slice(3)}` };
  }
  return { className: 'notes-hl-warm' };
}

/** Recovers ==tone:...== markup accidentally written inside code fences: only for ASCII-diagram rendering, never mutates the source. */
export function recoverTonedMarkup(text: string): string {
  const closed = hlToneClosedRegex();
  const open = hlTonePrefixRegex();
  let s = text;
  for (let n = 0; n < 16; n += 1) {
    const next = s.replace(closed, '$2');
    if (next === s) break;
    s = next;
  }
  s = s.replace(open, '');
  return s.replace(/(^|[^=])==(?!=)/gm, '$1');
}
