/**
 * @file CodeBlockOutput
 * @description Execution output panel of a fenced snippet: the verdict of the
 * last run (ok / error / timeout / cancelled / unavailable) plus the
 * captured stdout, stderr and failure detail.
 *
 * Responsibilities:
 * - Render the status pill of a settled run
 * - Render the captured streams and the truncation notice
 * - Offer the close action that dismisses the panel
 *
 * Constraints:
 * - The panel exists only while a run is in flight or a result is kept.
 * - The captured streams keep a fixed order: stdout, stderr, failure detail.
 */

import { useTranslation } from 'react-i18next';
import type { ExecutionResult } from '@/lib/code-runner';

/** i18n key per execution status (explicit map keeps lookups flat). */
const STATUS_KEYS = {
  ok: 'markdown.statusOk',
  error: 'markdown.statusError',
  timeout: 'markdown.statusTimeout',
  cancelled: 'markdown.statusCancelled',
  unavailable: 'markdown.statusUnavailable',
} as const;

/** Verdict badge of a settled run. */
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

export interface CodeBlockOutputProps {
  /** True while a run is in flight. */
  running: boolean;
  /** The settled outcome of the last run; null when there is none. */
  result: ExecutionResult | null;
  /** Drop the settled result and close the panel. */
  onClose: () => void;
}

/** Execution output panel of a fenced snippet. */
export function CodeBlockOutput({ running, result, onClose }: CodeBlockOutputProps) {
  const { t } = useTranslation('common');
  if (!running && !result) return null;
  return (
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
            onClick={onClose}
            aria-label={t('common:markdown.closeOutput')}
          >
            {t('common:markdown.closeOutput')}
          </button>
        )}
      </div>
      {result && (Boolean(result.output) || Boolean(result.stderr) || Boolean(result.error)) && (
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
  );
}
