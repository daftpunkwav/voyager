/**
 * @file LoadingSpinner
 * @description Spinner indicator with an accessible status label; renders inline or full screen.
 */

import { useTranslation } from 'react-i18next';
import { cn } from '@/utils/cn';

interface LoadingSpinnerProps {
  fullScreen?: boolean;
  label?: string;
}

export function LoadingSpinner({ fullScreen, label }: LoadingSpinnerProps) {
  const { t } = useTranslation('common');
  const text = label ?? t('state.loading');
  return (
    <div
      className={cn('loading-spinner', fullScreen && 'loading-spinner--fullscreen')}
      role="status"
      aria-label={text}
    >
      <div className="spinner" />
      {text && <span className="loading-spinner__label">{text}</span>}
    </div>
  );
}
