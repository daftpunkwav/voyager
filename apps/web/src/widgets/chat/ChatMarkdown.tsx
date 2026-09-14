/**
 * @file ChatMarkdown
 * @description In-chat Markdown rendering (GFM + highlight + allowlist
 * sanitize) shared by message bubbles, streaming paragraphs, artifact
 * previews and the inline turn trace.
 */

import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize';
import type { Options as SanitizeOptions } from 'rehype-sanitize';
import { safeHttpUrl, safeInternalPath } from '@/utils/safeUrl';

/** class names highlight.js may inject; same allowlist line as MarkdownRenderer (defense in depth). */
const sanitizeSchema: SanitizeOptions = {
  ...defaultSchema,
  attributes: {
    ...defaultSchema.attributes,
    code: [...(defaultSchema.attributes?.code ?? []), ['className']],
    span: [...(defaultSchema.attributes?.span ?? []), ['className']],
    pre: [...(defaultSchema.attributes?.pre ?? []), ['className']],
  },
};

const mdComponents: Components = {
  a({ href, children }) {
    const internal = safeInternalPath(href);
    if (internal) return <a href={internal}>{children}</a>;
    const http = safeHttpUrl(href);
    if (http) {
      return (
        <a href={http} target="_blank" rel="noopener noreferrer">
          {children}
        </a>
      );
    }
    return <span>{children}</span>;
  },
};

export function ChatMarkdown({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[rehypeHighlight, [rehypeSanitize, sanitizeSchema]]}
      components={mdComponents}
    >
      {content}
    </ReactMarkdown>
  );
}
