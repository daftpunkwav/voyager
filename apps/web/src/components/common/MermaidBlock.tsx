/**
 * @file MermaidBlock
 * @description Client-side Mermaid rendering into sanitized SVG; falls back to a plain code block on failure or when sanitization rejects the output.
 *
 * Responsibilities:
 * - Detect explicit mermaid fences and render them client-side into SVG
 * - Sanitize the SVG with DOMPurify and re-render on theme changes
 * - Fall back to a plain code block on failure or rejected output
 */

import { useEffect, useId, useState } from 'react';
import DOMPurify from 'dompurify';
import type { Config as DompurifyConfig } from 'dompurify';
import { useUIStore } from '@/stores/uiStore';
import { resolveTheme } from '@/shell/themeBridge';

/** Only explicit ```mermaid fences qualify, so ordinary code is never routed into the SVG injection path */
export function looksLikeMermaid(lang: string | null | undefined, _code?: string): boolean {
  return (lang || '').toLowerCase() === 'mermaid';
}

interface MermaidBlockProps {
  code: string;
}

const SVG_PURIFY: DompurifyConfig = {
  USE_PROFILES: { svg: true, svgFilters: true },
  ADD_TAGS: ['use'],
  FORBID_TAGS: ['script', 'foreignObject', 'iframe', 'object', 'embed', 'a'],
  FORBID_ATTR: ['onclick', 'onload', 'onerror', 'onmouseover', 'href', 'xlink:href'],
};

/**
 * Renders Mermaid source client-side into sanitized SVG.
 */
export function MermaidBlock({ code }: MermaidBlockProps) {
  const reactId = useId().replace(/:/g, '');
  const [svg, setSvg] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  // Resolve from the same source as data-theme so light themes no longer render dark-background SVG; theme changes trigger a re-render
  const mermaidTheme = resolveTheme(useUIStore((s) => s.theme));

  useEffect(() => {
    let cancelled = false;
    setSvg(null);
    setFailed(false);

    (async () => {
      try {
        const mermaid = (await import('mermaid')).default;
        mermaid.initialize({
          startOnLoad: false,
          // Mermaid's theme vocabulary has no 'light'; light maps to 'default'
          theme: mermaidTheme === 'dark' ? 'dark' : 'default',
          securityLevel: 'strict',
          fontFamily: 'inherit',
        });
        const { svg: rendered } = await mermaid.render(`mmd-${reactId}`, code);
        const clean = DOMPurify.sanitize(rendered, SVG_PURIFY);
        if (!clean || !clean.includes('<svg')) {
          throw new Error('svg sanitized empty');
        }
        if (!cancelled) setSvg(clean);
      } catch {
        if (!cancelled) {
          setFailed(true);
          setSvg(null);
        }
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [code, reactId, mermaidTheme]);

  if (failed || !svg) {
    return (
      <div className="md-codeblock md-mermaid--fallback" data-testid="mermaid-fallback">
        <div className="md-codeblock__lang">mermaid</div>
        <pre className="hljs">
          <code>{code}</code>
        </pre>
      </div>
    );
  }

  return (
    <div
      className="md-mermaid"
      data-testid="mermaid-svg"
      // The SVG has already been sanitized above via DOMPurify.sanitize(..., SVG_PURIFY)
      // eslint-disable-next-line no-restricted-syntax
      dangerouslySetInnerHTML={{ __html: svg }}
    />
  );
}
