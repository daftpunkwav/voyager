/**
 * @file noteHlGrammar
 * @description Behavior-level lock on the highlight tone grammar: every
 * palette tone must be recognized by each code path that consumes the
 * `==tone:` markup (parsing, fence recovery, outline stripping), so adding a
 * tone without updating the shared grammar factories fails loudly here.
 */

import { describe, expect, it } from 'vitest';
import {
  HL_TONE_AT,
  NOTE_HL_TONES,
  parseHlTone,
  parseNoteHighlight,
  recoverTonedMarkup,
} from '@/pages/notes/noteHl';
import { tocHeadingLabel } from '@/pages/notes/noteOutline';

describe('note highlight grammar', () => {
  it('recognizes every built-in tone at the tone position', () => {
    for (const tone of NOTE_HL_TONES) {
      expect(HL_TONE_AT.test(`${tone}:`)).toBe(true);
    }
    expect(HL_TONE_AT.test('rgb7c3aed:')).toBe(true);
    expect(HL_TONE_AT.test('nope:')).toBe(false);
  });

  it.each(NOTE_HL_TONES)('parses %s markup through parseNoteHighlight', (tone) => {
    const parsed = parseNoteHighlight(`==${tone}:body==`);
    expect(parsed).not.toBeNull();
    expect(parsed?.tone).toBe(tone);
    expect(parsed?.inner).toBe('body');
  });

  it.each(NOTE_HL_TONES)('strips %s markup in fence recovery', (tone) => {
    expect(recoverTonedMarkup(`==${tone}:body==`)).toBe('body');
  });

  it.each(NOTE_HL_TONES)('strips %s markup in outline heading labels', (tone) => {
    expect(tocHeadingLabel(`==${tone}:Head==`)).toBe('Head');
  });

  it('recognizes rgb tones through parseNoteHighlight', () => {
    expect(parseNoteHighlight('==rgb7c3aed:body==')?.tone).toBe('rgb7c3aed');
  });
});
