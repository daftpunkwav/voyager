/**
 * @file morse
 * @description Morse bit stream for the hero background letter animation: encodes the product name into dot/dash hop patterns.
 *
 * Responsibilities:
 * - Encode the brand word into a looping dot/dash bit stream (dot = low
 *   hop, dash = high hop, letter gaps inserted)
 * - Map each letter position and bit to hop amplitudes, invertible per
 *   cycle so repeats look different
 */

import { PRODUCT_NAME } from '@/brand';

/** Morse table (lowercase a-z). */
const MORSE: Record<string, string> = {
  a: '.-',
  b: '-...',
  c: '-.-.',
  d: '-..',
  e: '.',
  f: '..-.',
  g: '--.',
  h: '....',
  i: '..',
  j: '.---',
  k: '-.-',
  l: '.-..',
  m: '--',
  n: '-.',
  o: '---',
  p: '.--.',
  q: '--.-',
  r: '.-.',
  s: '...',
  t: '-',
  u: '..-',
  v: '...-',
  w: '.--',
  x: '-..-',
  y: '-.--',
  z: '--..',
};

/** Dot = 0 (low hop), dash = 1 (high hop). */
function encodeWord(word: string): (0 | 1)[] {
  const bits: (0 | 1)[] = [];
  for (const ch of word) {
    const pattern = MORSE[ch];
    if (!pattern) continue;
    if (bits.length > 0) bits.push(0);
    for (const symbol of pattern) {
      bits.push(symbol === '-' ? 1 : 0);
    }
  }
  return bits;
}

/** Morse bit stream played on a loop by the hero background letters: the brand word (@/brand PRODUCT_NAME, sourced from brand.json). */
export const HERO_MORSE_BITS = encodeWord(PRODUCT_NAME.toLowerCase());

/** Low/high hop amplitudes (px) per letter position, to create visual variety. */
const LOW_HOP_BY_LETTER = [6, 8, 5, 7, 6, 9, 5, 7, 6];
const HIGH_HOP_BY_LETTER = [17, 20, 15, 22, 18, 21, 16, 23, 19];

/** @param invert flips high/low on alternate cycles so each round looks different. */
export function getMorseHopPx(letterIndex: number, bit: 0 | 1, invert: boolean): number {
  const isHigh = invert ? bit === 0 : bit === 1;
  const table = isHigh ? HIGH_HOP_BY_LETTER : LOW_HOP_BY_LETTER;
  return table[letterIndex % table.length] ?? (isHigh ? 18 : 7);
}

export const HERO_MORSE_INTERVAL_MS = 1618;
