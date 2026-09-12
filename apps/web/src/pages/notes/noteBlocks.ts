/**
 * @file noteBlocks
 * @description Splits Markdown into selectable blocks for click-to-source in preview mode and split-pane navigation.
 *
 * Responsibilities:
 * - Partition Markdown into blocks (fences, headings, rules, list items,
 *   quotes, tables, paragraphs) with 1-based source line anchors
 * - Assign stable block ids for click-to-source mapping
 */

export interface MarkdownBlock {
  id: string;
  source: string;
  /** 1-based; the first line of the block in the Markdown source. */
  startLine: number;
}

export function splitMarkdownBlocks(md: string): MarkdownBlock[] {
  if (!md) return [];
  const lines = md.replace(/\r\n/g, '\n').split('\n');
  const chunks: { source: string; startLine: number }[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (line.trim() === '') {
      i += 1;
      continue;
    }
    const startLine = i + 1;
    if (/^```/.test(line)) {
      const buf = [line];
      i += 1;
      while (i < lines.length && !/^```/.test(lines[i])) {
        buf.push(lines[i]);
        i += 1;
      }
      if (i < lines.length) {
        buf.push(lines[i]);
        i += 1;
      }
      chunks.push({ source: buf.join('\n'), startLine });
      continue;
    }
    if (/^#{1,6}\s/.test(line) || /^(-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {
      chunks.push({ source: line, startLine });
      i += 1;
      continue;
    }
    if (/^\s*([-*+] |\d+\. |> )/.test(line)) {
      const buf = [line];
      i += 1;
      while (i < lines.length) {
        const next = lines[i];
        if (next.trim() === '') {
          if (i + 1 < lines.length && /^\s*([-*+] |\d+\. |> )/.test(lines[i + 1])) {
            buf.push(next);
            i += 1;
            continue;
          }
          break;
        }
        if (
          /^\s*([-*+] |\d+\. |> |\s+\S)/.test(next) ||
          /^```/.test(next) ||
          /^#{1,6}\s/.test(next)
        ) {
          if (/^```/.test(next) || /^#{1,6}\s/.test(next)) break;
          buf.push(next);
          i += 1;
          continue;
        }
        break;
      }
      chunks.push({ source: buf.join('\n'), startLine });
      continue;
    }
    if (/^\|/.test(line)) {
      const buf = [line];
      i += 1;
      while (i < lines.length && /^\|/.test(lines[i])) {
        buf.push(lines[i]);
        i += 1;
      }
      chunks.push({ source: buf.join('\n'), startLine });
      continue;
    }
    const buf = [line];
    i += 1;
    while (
      i < lines.length &&
      lines[i].trim() !== '' &&
      !/^#{1,6}\s/.test(lines[i]) &&
      !/^```/.test(lines[i]) &&
      !/^\s*([-*+] |\d+\. |> )/.test(lines[i]) &&
      !/^\|/.test(lines[i])
    ) {
      buf.push(lines[i]);
      i += 1;
    }
    chunks.push({ source: buf.join('\n'), startLine });
  }
  return chunks.map((c, idx) => ({ id: String(idx), source: c.source, startLine: c.startLine }));
}
