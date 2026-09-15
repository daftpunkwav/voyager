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
import { useNavigate } from 'react-router-dom';
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
    if (internal) return <InternalLink to={internal}>{children}</InternalLink>;
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

function InternalLink({ to, children }: { to: string; children: React.ReactNode }) {
  const navigate = useNavigate();
  return (
    <a
      href={to}
      onClick={(e) => {
        e.preventDefault();
        navigate(to);
      }}
    >
      {children}
    </a>
  );
}

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
