/**
 * @file MarkdownRenderer
 * @description Markdown renderer with GFM, syntax highlighting, sanitization, Mermaid, ASCII architecture diagrams, horizontal-scroll tables, heading anchors, code copy, image lightbox, [[wiki links]], and external links in new tabs.
 *
 * Security keeps rehype-sanitize as defense in depth; the schema is relaxed only
 * minimally (highlight className, attachment: and /api/ relative image sources,
 * and target/rel on anchors).
 *
 * Responsibilities:
 * - Render GFM Markdown with highlight.js coloring under a minimally relaxed schema
 * - Route mermaid fences to MermaidBlock and ASCII diagrams to a layer view
 * - Add heading anchors, code copy buttons and image lightbox handling
 * - Resolve wiki links and internal paths in-app; open external links in new tabs
 */

import { Children, memo, useState, type CSSProperties } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import ReactMarkdown, { type Options as MarkdownOptions } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import rehypeSanitize, { defaultSchema } from 'rehype-sanitize';
import type { Options as SanitizeOptions } from 'rehype-sanitize';
import GithubSlugger from 'github-slugger';
import { cn } from '@/utils/cn';
import { tryParseAsciiArchLayers, looksLikeMarkdownTable } from '@/utils/asciiArch';
import { extractCodeLang, nodeText } from '@/utils/markdownNodes';
import { looksLikeMermaid, MermaidBlock } from '@/components/common/MermaidBlock';
import { MdCodeBlock } from '@/components/common/MdCodeBlock';
import { Lightbox } from '@/components/common/Lightbox';
import { safeHttpUrl, safeImgSrc, safeInternalPath } from '@/utils/safeUrl';
import { routes } from '@/utils/routes';

interface MarkdownRendererProps {
  content: string;
  className?: string;
  /** Disables the table-in-code-block rescue pass on nested renders to avoid recursion */
  disableTableRescue?: boolean;
  /** Click callback for [[wiki links]]; when omitted, falls back to navigating to /notes?note=<id> by title (rendered dimmed) */
  onWikiLink?: (target: string) => void;
  /** Page-specific syntax (e.g. note highlights) injected here; default rendering (chat etc.) ships without it */
  remarkPlugins?: MarkdownOptions['remarkPlugins'];
  /** Page-private <mark> styling (note highlights); by default outputs the className as-is */
  markProps?: (className?: string) => { className: string; style?: CSSProperties };
  /** Recovers page markers mistakenly written inside code blocks; source text is unchanged by default */
  recoverCodeMarkup?: (text: string) => string;
}

/** Allows highlight.js-injected class names so sanitization does not strip coloring;
 *  keeps attachment: allowed in the schema as defense-in-depth (img src is
 *  rewritten upstream by safeImgSrc to site-relative /api/ URLs) and allows
 *  target/rel on anchors (external links in new tabs). */
const sanitizeSchema: SanitizeOptions = {
  ...defaultSchema,
  tagNames: [...(defaultSchema.tagNames ?? []), 'mark'],
  protocols: {
    ...defaultSchema.protocols,
    src: [...(defaultSchema.protocols?.src ?? []), 'attachment'],
  },
  attributes: {
    ...defaultSchema.attributes,
    // hast-util-sanitize's findDefinition is first-match-wins, so the
    // unrestricted className entry must precede the default code entry
    // ([className, /^language-./]) — appended after it, it would be dead and
    // the hljs class would be stripped from <code>.
    code: ['className', ...(defaultSchema.attributes?.code ?? [])],
    span: [...(defaultSchema.attributes?.span ?? []), 'className'],
    pre: [...(defaultSchema.attributes?.pre ?? []), 'className'],
    mark: [...(defaultSchema.attributes?.mark ?? []), 'className'],
    a: [...(defaultSchema.attributes?.a ?? []), 'target', 'rel'],
    h1: [...(defaultSchema.attributes?.h1 ?? []), 'id'],
    h2: [...(defaultSchema.attributes?.h2 ?? []), 'id'],
    h3: [...(defaultSchema.attributes?.h3 ?? []), 'id'],
    h4: [...(defaultSchema.attributes?.h4 ?? []), 'id'],
    h5: [...(defaultSchema.attributes?.h5 ?? []), 'id'],
    h6: [...(defaultSchema.attributes?.h6 ?? []), 'id'],
    // Plain string entries mean "attribute with any value"; the array form
    // ['className', 'loading'] would instead mean "className whose value is
    // exactly 'loading'" and would never allow the loading attribute.
    img: [...(defaultSchema.attributes?.img ?? []), 'className', 'loading'],
  },
};

/** Converts [[target|alias]] into Markdown links (#wiki: scheme); skips code fences (same semantics as the backend resolve_links). */
export function preprocessWikiLinks(content: string): string {
  const segments = content.split(/(```[\s\S]*?```|~~~[\s\S]*?~~~|`[^`\n]*`)/);
  const WIKI = /\[\[([^\]|\n]+)(?:\|([^\]\n]*))?\]\]/g;
  return segments
    .map((seg, i) => {
      if (i % 2 === 1) return seg; // Keep code fence / inline code segments verbatim
      return seg.replace(WIKI, (_m, target: string, alias?: string) => {
        const label = (alias ?? target).trim();
        return `[${label}](#wiki:${target.trim()})`;
      });
    })
    .join('');
}

function ArchStack({
  layers,
}: {
  layers: NonNullable<ReturnType<typeof tryParseAsciiArchLayers>>;
}) {
  const { t } = useTranslation('common');
  return (
    <div className="md-arch-stack" role="img" aria-label={t('common:markdown.archDiagram')}>
      {layers.map((layer, i) => (
        <div key={`${layer.title}-${i}`} className="md-arch-stack__layer">
          <div className="md-arch-stack__index">{i + 1}</div>
          <div className="md-arch-stack__body">
            <div className="md-arch-stack__title">{layer.title}</div>
            {layer.lines.length > 0 && (
              <ul className="md-arch-stack__lines">
                {layer.lines.map((line, j) => (
                  <li key={`${j}-${line.slice(0, 24)}`}>{line}</li>
                ))}
              </ul>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

function MarkdownRendererInner({
  content,
  className,
  disableTableRescue = false,
  onWikiLink,
  remarkPlugins,
  markProps,
  recoverCodeMarkup,
}: MarkdownRendererProps) {
  const { t } = useTranslation('common');
  const [lightbox, setLightbox] = useState<{ src: string; alt: string } | null>(null);
  const navigate = useNavigate();
  const slugs = new GithubSlugger();
  const prepared = preprocessWikiLinks(content);

  return (
    <div className={cn('markdown markdown-body', className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, ...(Array.isArray(remarkPlugins) ? remarkPlugins : [])]}
        rehypePlugins={[
          [rehypeHighlight, { detect: true, ignoreMissing: true }],
          [rehypeSanitize, sanitizeSchema],
        ]}
        components={{
          mark: ({ className: markCls, children, node: _node, style: _style, ...props }) => {
            const hl = markProps?.(markCls) ?? { className: markCls, style: undefined };
            return (
              <mark {...props} className={hl.className} style={hl.style}>
                {children}
              </mark>
            );
          },
          h1: ({ children, ...props }) => {
            const id = slugs.slug(nodeText(children));
            return (
              <h1 {...props} id={id}>
                {children}
              </h1>
            );
          },
          h2: ({ children, ...props }) => {
            const id = slugs.slug(nodeText(children));
            return (
              <h2 {...props} id={id}>
                {children}
              </h2>
            );
          },
          h3: ({ children, ...props }) => {
            const id = slugs.slug(nodeText(children));
            return (
              <h3 {...props} id={id}>
                {children}
              </h3>
            );
          },
          h4: ({ children, ...props }) => {
            const id = slugs.slug(nodeText(children));
            return (
              <h4 {...props} id={id}>
                {children}
              </h4>
            );
          },
          h5: ({ children, ...props }) => {
            const id = slugs.slug(nodeText(children));
            return (
              <h5 {...props} id={id}>
                {children}
              </h5>
            );
          },
          h6: ({ children, ...props }) => {
            const id = slugs.slug(nodeText(children));
            return (
              <h6 {...props} id={id}>
                {children}
              </h6>
            );
          },
          a: ({ children, href, ...props }) => {
            if (typeof href === 'string' && href.startsWith('#wiki:')) {
              let target = href.slice('#wiki:'.length);
              try {
                target = decodeURIComponent(target);
              } catch {
                /* Invalid percent-encoding: fall back to the raw string as the title */
              }
              target = target.trim();
              if (!target) return <span>{children}</span>;
              const to = routes.note(target);
              return (
                <a
                  {...props}
                  href={to}
                  className="md-wiki-link"
                  title={t('common:markdown.wikiLinkTitle', { target })}
                  onClick={(e) => {
                    e.preventDefault();
                    if (onWikiLink) onWikiLink(target);
                    else navigate(to);
                  }}
                >
                  {children}
                </a>
              );
            }
            const internal = typeof href === 'string' ? safeInternalPath(href) : null;
            if (internal) {
              return (
                <a
                  {...props}
                  href={internal}
                  onClick={(e) => {
                    e.preventDefault();
                    navigate(internal);
                  }}
                >
                  {children}
                </a>
              );
            }
            const safe = typeof href === 'string' ? safeHttpUrl(href) : undefined;
            if (!safe) {
              return <span>{children}</span>;
            }
            return (
              <a {...props} href={safe} target="_blank" rel="noreferrer noopener">
                {children}
              </a>
            );
          },
          img: ({ src, alt, ...props }) => {
            const resolved = safeImgSrc(
              typeof src === 'string' && src.startsWith('attachment://') ? src : src
            );
            if (!resolved) return null;
            return (
              <img
                {...props}
                src={resolved}
                alt={alt ?? ''}
                loading="lazy"
                className="md-img"
                onClick={() => setLightbox({ src: resolved, alt: alt ?? '' })}
              />
            );
          },
          table: ({ children, ...props }) => (
            <div className="markdown-table-wrap">
              <table {...props}>{children}</table>
            </div>
          ),
          pre: ({ children }) => {
            const text = Children.toArray(children).map(nodeText).join('');
            // A Markdown table mistakenly pasted into a code block: re-render it as Markdown instead of treating it as an architecture card or plain text
            if (!disableTableRescue && looksLikeMarkdownTable(text)) {
              return (
                <div className="md-table-rescue">
                  <MarkdownRenderer
                    content={text}
                    disableTableRescue
                    remarkPlugins={remarkPlugins}
                    markProps={markProps}
                    recoverCodeMarkup={recoverCodeMarkup}
                    onWikiLink={onWikiLink}
                  />
                </div>
              );
            }
            const recovered = recoverCodeMarkup ? recoverCodeMarkup(text) : text;
            const layers =
              tryParseAsciiArchLayers(text) ??
              (recovered !== text ? tryParseAsciiArchLayers(recovered) : null);
            if (layers) return <ArchStack layers={layers} />;
            const lang = extractCodeLang(children);
            if (looksLikeMermaid(lang, text)) {
              return <MermaidBlock code={recovered} />;
            }
            return (
              <MdCodeBlock lang={lang} text={text}>
                {children}
              </MdCodeBlock>
            );
          },
        }}
      >
        {prepared}
      </ReactMarkdown>
      <Lightbox src={lightbox?.src ?? null} alt={lightbox?.alt} onClose={() => setLightbox(null)} />
    </div>
  );
}

export const MarkdownRenderer = memo(MarkdownRendererInner);
