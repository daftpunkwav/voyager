/**
 * @file ChatMarkdown
 * @description In-chat Markdown rendering (GFM + highlight + allowlist
 * sanitize) shared by message bubbles, streaming paragraphs, artifact
 * previews and the inline turn trace. Code fences get the shared block
 * chrome (language label / copy / optional run), mermaid fences render as
 * diagrams, and tables are wrapped for horizontal scrolling.
 */

import { memo } from 'react';
import ReactMarkdown, { type Components } from 'react-markdown';
import type { Pluggable } from 'unified';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize';
import type { Options as SanitizeOptions } from 'rehype-sanitize';
import { useNavigate } from 'react-router-dom';
import { safeHttpUrl, safeInternalPath } from '@/utils/safeUrl';
import { extractCodeLang, nodeText } from '@/utils/markdownNodes';
import { looksLikeMermaid, MermaidBlock } from '@/components/common/MermaidBlock';
import { MdCodeBlock } from '@/components/common/MdCodeBlock';

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

/** `runCode` gates the execute button on code fences; trace views pass false
 *  so historical tool output stays copy-only. */
const mdComponents = (runCode: boolean): Components => ({
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
  table({ children, ...props }) {
    return (
      <div className="markdown-table-wrap">
        <table {...props}>{children}</table>
      </div>
    );
  },
  pre({ children }) {
    // The fence source ends with the newline before the closing ```; strip it
    // so copy/run see the snippet the user wrote.
    const text = nodeText(children).replace(/\n$/, '');
    const lang = extractCodeLang(children);
    if (looksLikeMermaid(lang, text)) {
      return <MermaidBlock code={text} />;
    }
    return (
      <MdCodeBlock lang={lang} text={text} runCode={runCode}>
        {children}
      </MdCodeBlock>
    );
  },
});

/** Two frozen component maps (run on/off) so memoized renders never rebuild
 *  the components object. */
const COMPONENTS: Record<'run' | 'readonly', Components> = {
  run: mdComponents(true),
  readonly: mdComponents(false),
};

/** Memoized on `content`: streaming frames re-render the whole message list
 *  (MessageList subscribes to `streaming`, so every agent.delta re-renders all
 *  bubbles) while historical messages keep identical content. Memo lets React
 *  skip the full remark/rehype pipeline for unchanged text — that repeated
 *  parsing dominates per-delta render cost in long conversations. Output is a
 *  pure function of `content`, so shallow prop comparison is safe. */
/** Same highlight options as MarkdownRenderer: detect fence languages and
 *  ignore unknown ones instead of crashing the render. */
const highlightPlugin: Pluggable = [rehypeHighlight, { detect: true, ignoreMissing: true }];

export const ChatMarkdown = memo(function ChatMarkdown({
  content,
  runCode = true,
}: {
  content: string;
  runCode?: boolean;
}) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      rehypePlugins={[highlightPlugin, [rehypeSanitize, sanitizeSchema]]}
      components={COMPONENTS[runCode ? 'run' : 'readonly']}
    >
      {content}
    </ReactMarkdown>
  );
});
