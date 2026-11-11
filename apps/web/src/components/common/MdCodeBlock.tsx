/**
 * @file MdCodeBlock
 * @description Shared fenced-code block chrome used by every markdown
 * renderer (chat bubbles, notes, artifacts): language label, copy button,
 * optional run button (python / javascript / typescript — other languages are
 * copy-only), and an execution output panel. Syntax highlighting arrives via
 * `children` (the renderer's highlight pass); execution engines stay behind
 * the code-runner registry.
 *
 * The chrome parts live next to this file under `codeblock/`: the copy
 * button, the language badge, the output panel and the run-lifecycle hook.
 */

import { memo, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { isRunnable } from '@/lib/code-runner';
import { CodeBlockCopyButton } from '@/components/common/codeblock/CodeBlockCopyButton';
import { CodeBlockLanguageBadge } from '@/components/common/codeblock/CodeBlockLanguageBadge';
import { CodeBlockOutput } from '@/components/common/codeblock/CodeBlockOutput';
import { useCodeExecution } from '@/components/common/codeblock/useCodeExecution';

export interface MdCodeBlockProps {
  /** Fence language id (already lowercased); null for unlabeled blocks. */
  lang?: string | null;
  /** Raw source text — used for copy and execution, never for rendering. */
  text: string;
  /** Pre-highlighted `<code>` element from the renderer's highlight pass. */
  children: ReactNode;
  /** When false the run button is omitted (trace views, embedded previews). */
  runCode?: boolean;
}

/** Code block chrome: actions bar + highlighted source + optional run output. */
export const MdCodeBlock = memo(function MdCodeBlock({
  lang,
  text,
  children,
  runCode = true,
}: MdCodeBlockProps) {
  const { t } = useTranslation('common');
  const { running, result, run, stop, dismiss } = useCodeExecution(lang, text);
  const runnable = runCode && isRunnable(lang ?? undefined);

  return (
    <div className="md-codeblock">
      <div className="md-codeblock__bar">
        <div className="md-codeblock__actions">
          {runnable && !running && (
            <button
              type="button"
              className="md-codeblock__btn"
              onClick={run}
              aria-label={t('common:markdown.run')}
            >
              {t('common:markdown.run')}
            </button>
          )}
          {runnable && running && (
            <button
              type="button"
              className="md-codeblock__btn"
              onClick={stop}
              aria-label={t('common:markdown.stop')}
            >
              {t('common:markdown.stop')}
            </button>
          )}
          <CodeBlockCopyButton text={text} />
        </div>
        <CodeBlockLanguageBadge lang={lang} />
      </div>
      <pre className="hljs">{children}</pre>
      <CodeBlockOutput running={running} result={result} onClose={dismiss} />
    </div>
  );
});
