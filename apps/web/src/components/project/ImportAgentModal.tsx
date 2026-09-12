/**
 * @file ImportAgentModal
 * @description Shared import/sync modal shell: business content on the left, an AI agent panel on the right.
 *
 * Responsibilities:
 * - Lay out business content and the optional agent panel side by side
 * - Provide the modal chrome: header, close button, overlay click to cancel
 * - Support a large size variant and an agent-less layout
 */

import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

interface ImportAgentModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  size?: 'default' | 'large';
  children: ReactNode;
  /** Agent panel; omit to collapse the right side when unavailable */
  agentPanel?: ReactNode;
}

/** Import/sync modal shell: left business area : right agent = 1.168 : 1 */
export function ImportAgentModal({
  open,
  onClose,
  title,
  subtitle,
  size = 'default',
  children,
  agentPanel,
}: ImportAgentModalProps) {
  const { t } = useTranslation('sources');
  if (!open) return null;

  return (
    <div className="modal-overlay import-modal-overlay" role="presentation" onClick={onClose}>
      <div
        className={`import-agent-modal glass-card glass-card--dialog ${size === 'large' ? 'import-agent-modal--large' : ''}${!agentPanel ? ' import-agent-modal--no-agent' : ''}`}
        role="dialog"
        aria-labelledby="import-modal-title"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="import-agent-modal__header">
          <div>
            <h2 id="import-modal-title">{title}</h2>
            {subtitle && <p>{subtitle}</p>}
          </div>
          <button
            type="button"
            className="chat-icon-btn"
            onClick={onClose}
            aria-label={t('sources:closeAria')}
          >
            ×
          </button>
        </header>
        <div className="import-agent-modal__body">
          <div className="import-agent-modal__biz">{children}</div>
          {agentPanel && <div className="import-agent-modal__agent">{agentPanel}</div>}
        </div>
      </div>
    </div>
  );
}
