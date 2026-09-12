/**
 * @file GraphGuidePanel
 * @description Floating Atlas guide: avatar button that toggles an embedded agent chat panel.
 *
 * Responsibilities:
 * - Toggle the embedded agent chat panel from a floating avatar button
 * - Track pointer movement while closed so the avatar eyes follow the cursor
 */
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { EmbedAgentChat } from '@/widgets/chat/EmbedAgentChat';
import { AgentAvatar, type LookTarget } from '@/components/agent/AgentAvatar';

interface GraphGuidePanelProps {
  selectedNodeId: string | null;
}

/**
 * Floating Atlas button: an avatar in the bottom-right corner that toggles
 * the chat panel on click. While closed, the avatar's eyes follow the pointer.
 */
export function GraphGuidePanel({ selectedNodeId }: GraphGuidePanelProps) {
  const { t } = useTranslation('graph');
  const [open, setOpen] = useState(false);
  const [lookTarget, setLookTarget] = useState<LookTarget | null>(null);

  useEffect(() => {
    if (open) {
      setLookTarget(null);
      return;
    }

    const onPointerMove = (event: PointerEvent) => {
      setLookTarget({ x: event.clientX, y: event.clientY });
    };

    window.addEventListener('pointermove', onPointerMove, { passive: true });
    return () => window.removeEventListener('pointermove', onPointerMove);
  }, [open]);

  return (
    <div className={`atlas-scout${open ? ' is-open' : ''}`}>
      {open && (
        <div
          className="atlas-scout__panel glass-card glass-card--panel"
          role="dialog"
          aria-label={t('graph:guide.dialogAria')}
        >
          <header className="atlas-scout__head">
            <div>
              <strong>{t('graph:guide.title')}</strong>
              <p>{t('graph:guide.tagline')}</p>
            </div>
            <button
              type="button"
              className="atlas-scout__close"
              onClick={() => setOpen(false)}
              aria-label={t('graph:guide.close')}
            >
              ×
            </button>
          </header>
          <div className="atlas-scout__body">
            <EmbedAgentChat
              mode="graph"
              title="Atlas"
              subtitle=""
              agentInitial="A"
              agentClassName="agent-graph_guide"
              graphNodeId={selectedNodeId}
              placeholder={t('graph:guide.placeholder')}
            />
          </div>
        </div>
      )}
      <button
        type="button"
        className="atlas-scout__fab"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label={open ? t('graph:guide.close') : t('graph:guide.open')}
        title={open ? t('graph:guide.close') : t('graph:guide.open')}
      >
        <AgentAvatar agentId="navigator" lookTarget={lookTarget} isFocused={open} blink size={56} />
        <span className="atlas-scout__fab-label">Atlas</span>
      </button>
    </div>
  );
}
