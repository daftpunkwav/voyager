/**
 * @file Degraded.tsx
 * @description Unified degraded state: error code + explanation + remediation hint + retry.
 */

import { useTranslation } from 'react-i18next';

interface DegradedProps {
  code: string;
  message: string;
  hint?: string;
  onRetry?: () => void;
}

export function Degraded({ code, message, hint, onRetry }: DegradedProps) {
  const { t } = useTranslation('common');
  return (
    <div className="degraded" role="alert">
      <div className="degraded__code mono">{code}</div>
      <div className="degraded__message">{message}</div>
      {hint ? <div className="degraded__hint small muted">{hint}</div> : null}
      {onRetry ? (
        <button type="button" className="btn" onClick={onRetry}>
          {t('action.retry')}
        </button>
      ) : null}
    </div>
  );
}
