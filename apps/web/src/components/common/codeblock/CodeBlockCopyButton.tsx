/**
 * @file CodeBlockCopyButton
 * @description Clipboard action of a fenced snippet. The button owns its
 * transient "copied" acknowledgement so the code-block chrome does not have
 * to carry that state.
 *
 * Responsibilities:
 * - Write the snippet source to the clipboard on click
 * - Show the copied acknowledgement for a fixed window, then revert to the
 *   copy label
 *
 * Constraints:
 * - A clipboard failure (insecure context) must not fake success: the label
 *   stays unchanged.
 * - The button renders i18n labels only, never inline copy.
 */

import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

/** Feedback duration for the copied state. */
const COPIED_RESET_MS = 1500;

export interface CodeBlockCopyButtonProps {
  /** Raw source text written to the clipboard. */
  text: string;
}

/** Clipboard action for a fenced snippet. */
export function CodeBlockCopyButton({ text }: CodeBlockCopyButtonProps) {
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
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        navigator.clipboard
          .writeText(text)
          .then(() => {
            setCopied(true);
            // Clear the previous timer on rapid clicks, otherwise the earlier reset would cut the second "copied" state short
            if (timerRef.current != null) window.clearTimeout(timerRef.current);
            timerRef.current = window.setTimeout(() => setCopied(false), COPIED_RESET_MS);
          })
          .catch(() => {
            /* Clipboard unavailable (insecure context): keep button state unchanged instead of faking success */
          });
      }}
    >
      {copied ? t('common:markdown.copied') : t('common:markdown.copy')}
    </button>
  );
}
