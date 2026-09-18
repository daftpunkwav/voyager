/**
 * @file Shared react-markdown node helpers used by the markdown renderers:
 * text extraction from element children and fence-language detection from
 * highlight.js class names.
 */

import { Children, isValidElement, type ReactNode } from 'react';

export function nodeText(node: ReactNode): string {
  if (node == null || typeof node === 'boolean') return '';
  if (typeof node === 'string' || typeof node === 'number') return String(node);
  if (Array.isArray(node)) return node.map(nodeText).join('');
  if (isValidElement<{ children?: ReactNode }>(node)) {
    return nodeText(node.props.children);
  }
  return '';
}

/** Fence language from the `language-x` / `hljs x` class rehype-highlight adds. */
export function extractCodeLang(children: ReactNode): string | null {
  for (const child of Children.toArray(children)) {
    if (!isValidElement<{ className?: string }>(child)) continue;
    const cls = child.props.className ?? '';
    const m = /\blanguage-([a-z0-9_+-]+)\b/i.exec(cls) || /\bhljs\s+([a-z0-9_+-]+)\b/i.exec(cls);
    if (m?.[1] && m[1].toLowerCase() !== 'hljs') return m[1].toLowerCase();
  }
  return null;
}
