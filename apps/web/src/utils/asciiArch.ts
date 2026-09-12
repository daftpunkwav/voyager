/**
 * @file asciiArch
 * @description Detects bordered ASCII architecture diagrams and parses them into
 * layers so monospace alignment survives mixed-width text.
 *
 * Must never swallow Markdown pipe tables; those are rejected before parsing.
 *
 * Responsibilities:
 * - Detect bordered ASCII box diagrams (border lines plus pipe content)
 *   while rejecting GFM pipe tables first
 * - Parse detected diagrams into titled layer lists with box padding
 *   stripped
 *
 * This module must not depend on UI-layer components.
 */

export interface AsciiArchLayer {
  title: string;
  lines: string[];
}

/** GFM header separator rows like |---|---| or | :--- | ---: | */
function isMarkdownTableSeparator(line: string): boolean {
  const t = line.trim();
  if (!t.includes('-') || !t.includes('|')) return false;
  // After stripping cells, only pipes, colons, dashes and whitespace should remain
  const stripped = t.replace(/[\s|:-]/g, '');
  return stripped.length === 0 && (t.match(/\|/g) ?? []).length >= 2;
}

/** Multi-column table row (at least two pipe separators). */
function isMarkdownTableRow(line: string): boolean {
  const t = line.trim();
  if (!t.includes('|')) return false;
  const pipes = (t.match(/\|/g) ?? []).length;
  // "| a | b |" carries at least 2 pipes
  return pipes >= 2;
}

export function looksLikeMarkdownTable(text: string): boolean {
  const lines = text
    .replace(/\r\n/g, '\n')
    .trim()
    .split('\n')
    .map((l) => l.trim())
    .filter(Boolean);
  if (lines.length < 2) return false;
  const sepIdx = lines.findIndex(isMarkdownTableSeparator);
  if (sepIdx < 0) return false;
  // Table rows should sit right around the separator row
  const headerLine = lines[sepIdx - 1];
  const hasHeader = sepIdx > 0 && headerLine !== undefined && isMarkdownTableRow(headerLine);
  const bodyRows = lines.slice(sepIdx + 1).filter(isMarkdownTableRow);
  return hasHeader && (bodyRows.length >= 1 || lines.length <= 3);
}

function isBoxBorderLine(line: string): boolean {
  const t = line.trim();
  if (!t) return false;
  // +---+ / box-drawing borders (real frame lines, not |---|---| table separators)
  if (/^[+┌├└┬┴][-─=━]{2,}[+┐┤┘]?$/.test(t)) return true;
  if (/^[┌├└][─\s]{2,}[┐┤┘]$/.test(t)) return true;
  if (/^[+=\-─━]{4,}$/.test(t)) return true;
  return false;
}

function stripBoxPadding(line: string): string {
  return line
    .replace(/^\s*[|│]\s?/, '')
    .replace(/\s*[|│]\s*$/, '')
    .replace(/\s+$/g, '');
}

function looksLikeAsciiBox(text: string): boolean {
  if (looksLikeMarkdownTable(text)) return false;

  const lines = text.replace(/\r\n/g, '\n').trim().split('\n');
  if (lines.length < 4) return false;

  let borders = 0;
  let pipeContent = 0;
  for (const line of lines) {
    if (isBoxBorderLine(line)) {
      borders += 1;
      continue;
    }
    // Pipe-prefixed content lines: "| .... |" or "| ...." (right side may be ragged)
    const t = line.trim();
    if (/^[|│]/.test(t) && !isMarkdownTableSeparator(t)) {
      // Markdown tables also look like pipe rows, but the whole text was already
      // screened against tables before we get here, so counting is safe.
      pipeContent += 1;
    }
  }
  // Require genuine +--- / box-drawing borders, not just pipe rows
  return borders >= 2 && pipeContent >= 2;
}

/**
 * Try to parse a bordered ASCII diagram into a layer list; return null if the
 * text does not look like a box diagram.
 */
export function tryParseAsciiArchLayers(text: string): AsciiArchLayer[] | null {
  const raw = text.replace(/\r\n/g, '\n').trim();
  if (!raw || !looksLikeAsciiBox(raw)) return null;

  const lines = raw.split('\n');
  const layers: AsciiArchLayer[] = [];
  let bucket: string[] = [];

  const flush = () => {
    const cleaned = bucket
      .map(stripBoxPadding)
      .map((l) => l.trimEnd())
      .filter((l) => l.trim().length > 0);
    bucket = [];
    if (!cleaned.length) return;
    const title = cleaned[0]?.trim() ?? '';
    const rest = cleaned
      .slice(1)
      .map((l) => l.trim())
      .filter(Boolean);
    layers.push({ title, lines: rest });
  };

  for (const line of lines) {
    if (isBoxBorderLine(line)) {
      flush();
      continue;
    }
    if (/^\s*[|│]/.test(line) || bucket.length > 0) {
      bucket.push(line);
    }
  }
  flush();

  if (layers.length < 2) return null;
  return layers;
}
