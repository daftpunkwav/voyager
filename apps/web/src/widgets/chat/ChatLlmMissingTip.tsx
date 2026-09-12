/**
 * @file ChatLlmMissingTip
 * @description Shared tip shown when no usable LLM key is confirmed (chat page /
 * floating window / embedded chat panels).
 */

import { Link } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { routes } from '@/utils/routes';

export function ChatLlmMissingTip() {
  const { t } = useTranslation('chat');
  return (
    <div className="degrade-tip" role="status">
      <span>
        {t('chat:llmMissing.before')} <Link to={routes.settings}>{t('chat:llmMissing.link')}</Link>{' '}
        {t('chat:llmMissing.after')}
      </span>
    </div>
  );
}
