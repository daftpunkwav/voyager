/**
 * @file MdCodeBlock
 * @description Shared fenced-code block chrome used by every markdown
 * renderer (chat bubbles, notes, artifacts): language label, copy button,
 * optional run button (python / javascript / typescript — other languages are
 * copy-only), and an execution output panel. Syntax highlighting arrives via
 * `children` (the renderer's highlight pass); execution engines stay behind
 * the code-runner registry.
 */

import { memo, useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import {
  getRunner,
  isRunnable,
  type ExecutionHandle,
  type ExecutionResult,
} from '@/lib/code-runner';

/** Feedback duration for the copied state. */
const COPIED_RESET_MS = 1500;

function CodeCopyButton({ text }: { text: string }) {
  const { t } = useTranslation('common');
  const [copied, setCopied] = useState(false);
  const timerRef = useRef<number | null>(null);
  useEffect(
    () => () => {
      if (timerRef.current != null) window.clearTimeout(timerRef.current);
    },
    []
  );
  return (
    <button
      type="button"
      className="md-codeblock__btn"
      aria-label={t('common:markdown.copyCode')}
      onClick={async (e) => {
        e.preventDefault();
        e.stopPropagation();
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          // Clear the previous timer on rapid clicks, otherwise the earlier reset would cut the second "copied" state short
          if (timerRef.current != null) window.clearTimeout(timerRef.current);
          timerRef.current = window.setTimeout(() => setCopied(false), COPIED_RESET_MS);
        } catch {
          /* Clipboard unavailable (insecure context): keep button state unchanged instead of faking success */
        }
      }}
    >
      {copied ? t('common:markdown.copied') : t('common:markdown.copy')}
    </button>
  );
}

/** i18n key per execution status (explicit map keeps lookups flat). */
const STATUS_KEYS = {
  ok: 'markdown.statusOk',
  error: 'markdown.statusError',
  timeout: 'markdown.statusTimeout',
  cancelled: 'markdown.statusCancelled',
  unavailable: 'markdown.statusUnavailable',
} as const;

function StatusPill({ result }: { result: ExecutionResult }) {
  const { t } = useTranslation('common');
  const tone =
    result.status === 'ok'
      ? 'ok'
      : result.status === 'timeout' || result.status === 'error'
        ? 'error'
        : '';
  return (
    <span
      className={`md-codeblock__status${tone ? ` md-codeblock__status--${tone}` : ''}`}
      role="status"
    >
      {t(`common:${STATUS_KEYS[result.status]}`)} ·{' '}
      {t('common:markdown.durationMs', { ms: result.durationMs })}
    </span>
  );
}

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
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<ExecutionResult | null>(null);
  const runRef = useRef<{ generation: number; handle: ExecutionHandle | null }>({
    generation: 0,
    handle: null,
  });

  // A new snippet resets prior execution state; stale runs are ignored.
  useEffect(() => {
    runRef.current.generation += 1;
    try {
      runRef.current.handle?.cancel();
    } catch {
      /* already settled */
    }
    runRef.current.handle = null;
    setRunning(false);
    setResult(null);
  }, [text, lang]);

  // Abort in-flight runs on unmount (frees workers, drops late results).
  useEffect(
    () => () => {
      runRef.current.generation += 1;
      try {
        runRef.current.handle?.cancel();
      } catch {
        /* already settled */
      }
    },
    []
  );

  const onRun = useCallback(() => {
    const runner = getRunner(lang ?? undefined);
    if (!runner) return;
    const generation = runRef.current.generation + 1;
    runRef.current.generation = generation;
    try {
      runRef.current.handle?.cancel();
    } catch {
      /* already settled */
    }
    setResult(null);
    setRunning(true);
    const handle = runner.run(text);
    runRef.current.handle = handle;
    void handle.done.then((outcome) => {
      if (runRef.current.generation !== generation) return;
      runRef.current.handle = null;
      setRunning(false);
      setResult(outcome);
    });
  }, [lang, text]);

  const onStop = useCallback(() => {
    try {
      runRef.current.handle?.cancel();
    } catch {
      /* already settled */
    }
  }, []);

  const runnable = runCode && isRunnable(lang ?? undefined);

  return (
    <div className="md-codeblock">
      <div className="md-codeblock__bar">
        <div className="md-codeblock__actions">
          {runnable && !running && (
            <button
              type="button"
              className="md-codeblock__btn"
              onClick={onRun}
              aria-label={t('common:markdown.run')}
            >
              {t('common:markdown.run')}
            </button>
          )}
          {runnable && running && (
            <button
              type="button"
              className="md-codeblock__btn"
              onClick={onStop}
              aria-label={t('common:markdown.stop')}
            >
              {t('common:markdown.stop')}
            </button>
          )}
          <CodeCopyButton text={text} />
        </div>
        {lang ? <div className="md-codeblock__lang">{lang}</div> : null}
      </div>
      <pre className="hljs">{children}</pre>
      {(running || result) && (
        <div className="md-codeblock__output">
          <div className="md-codeblock__output-head">
            <span className="md-codeblock__output-label">{t('common:markdown.output')}</span>
            {running && (
              <span className="md-codeblock__status" role="status">
                {t('common:markdown.running')}
              </span>
            )}
            {result && <StatusPill result={result} />}
            {!running && result && (
              <button
                type="button"
                className="md-codeblock__btn"
                onClick={() => setResult(null)}
                aria-label={t('common:markdown.closeOutput')}
              >
                {t('common:markdown.closeOutput')}
              </button>
            )}
          </div>
          {result && (result.output || result.stderr || result.error) && (
            <div className="md-codeblock__output-body">
              {result.output && (
                <pre className="md-codeblock__output-pre">
                  <code>{result.output}</code>
                </pre>
              )}
              {result.stderr && (
                <pre className="md-codeblock__output-pre md-codeblock__output-pre--stderr">
                  <code>{result.stderr}</code>
                </pre>
              )}
              {result.error && (
                <pre className="md-codeblock__output-pre md-codeblock__output-pre--error">
                  <code>{result.error}</code>
                </pre>
              )}
              {result.truncated && (
                <p className="md-codeblock__output-note">{t('common:markdown.truncated')}</p>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
});
