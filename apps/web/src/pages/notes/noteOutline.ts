/**
 * @file noteOutline
 * @description Note table-of-contents extraction with the same semantics as the backend extract_toc (skips fences, 1-based line numbers).
 *
 * Responsibilities:
 * - Extract headings (level / text / 1-based line) while skipping fenced
 *   blocks, matching backend extract_toc semantics
 * - Provide the visible heading label with highlight markers stripped for
 *   TOC display and slug generation
 */

import { NOTE_HL_KIND } from './noteHl';

export interface NoteTocItem {
  level: number;
  text: string;
  line: number;
}

export function extractNoteToc(content: string): NoteTocItem[] {
  const toc: NoteTocItem[] = [];
  let inFence = false;
  let fenceMarker = '';
  const lines = content.replace(/\r\n/g, '\n').split('\n');
  for (let i = 0; i < lines.length; i += 1) {
    const stripped = lines[i].replace(/^\s+/, '');
    const marker = stripped.slice(0, 3);
    if (marker === '```' || marker === '~~~') {
      if (!inFence) {
        inFence = true;
        fenceMarker = marker;
      } else if (marker === fenceMarker) {
        inFence = false;
      }
      continue;
    }
    if (inFence || !stripped.startsWith('#')) continue;
    const m = /^(#{1,6})\s+(.+?)\s*#*\s*$/.exec(stripped);
    if (m) toc.push({ level: m[1].length, text: m[2].trim(), line: i + 1 });
  }
  return toc;
}

/** TOC display and slug generation use the visible heading with highlight markers stripped, matching the preview node text. */
export function tocHeadingLabel(text: string): string {
  const stripped = text
    .replace(new RegExp(`==(${NOTE_HL_KIND}):`, 'gi'), '')
    .replace(/==/g, '')
    .trim();
  return stripped || text;
}
