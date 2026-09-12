/**
 * @file noteMarkDiff
 * @description Computes the minimal replacement interval between two documents for a single CodeMirror dispatch.
 */

export function diffReplace(
  oldText: string,
  next: string
): { from: number; to: number; insert: string } {
  let a = 0;
  const max = Math.min(oldText.length, next.length);
  while (a < max && oldText[a] === next[a]) a += 1;
  let bOld = oldText.length;
  let bNew = next.length;
  while (bOld > a && bNew > a && oldText[bOld - 1] === next[bNew - 1]) {
    bOld -= 1;
    bNew -= 1;
  }
  return { from: a, to: bOld, insert: next.slice(a, bNew) };
}
