/**
 * @file SubagentRunDialog
 * @description Execution view for one dispatched subagent: goal, live status
 * and the full step/thinking trail, rendered with the same trace components
 * the main agent's trajectory uses. Steps come from the run-scoped slice of
 * chatStore (hydrated from /api/chat/trajectory?run_id on open, appended live
 * by the AGENT_STEP dispatch), so the view updates in place while the run
 * progresses.
 */

import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ModalOverlay } from '@/components/common/ModalOverlay';
import { ClosedTurnTrace } from '@/widgets/chat/TurnTrace';
import { fetchRunSteps, interruptInstance } from '@/bridge/chatSend';
import { useChatStore } from '@/stores/chatStore';
import { formatDurationSec } from '@/utils/trajectory';

/** Minimal shape of a list_subagents.running entry (see RightPanel). */
export interface SubagentRunRef {
  id: string;
  run_id?: string;
  name: string;
  status: string;
  goal: string;
  started_ts: number;
  conversational?: boolean;
}

interface SubagentRunDialogProps {
  instance: SubagentRunRef | null;
  open: boolean;
  onClose: () => void;
}

export function SubagentRunDialog({ instance, open, onClose }: SubagentRunDialogProps) {
  const { t } = useTranslation('chat');
  const runId = instance?.run_id ?? '';
  const stored = useChatStore((s) => (runId ? s.runSteps[runId] : undefined));
  const steps = useMemo(() => stored ?? [], [stored]);
  const [hydrated, setHydrated] = useState(false);
  const [now, setNow] = useState(() => Date.now());

  useEffect(() => {
    if (!open || !runId) return;
    setHydrated(false);
    let alive = true;
    fetchRunSteps(runId)
      .then((events) => {
        if (alive) {
          useChatStore.getState().hydrateRunSteps(runId, events);
          setHydrated(true);
        }
      })
      .catch(() => {
        if (alive) setHydrated(true); // live steps alone still work
      });
    return () => {
      alive = false;
    };
  }, [open, runId]);

  // Elapsed clock ticks while the run is still going.
  const running = instance?.status === 'running';
  useEffect(() => {
    if (!open || !running) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [open, running]);

  const elapsed = useMemo(() => {
    if (!instance || !instance.started_ts) return '';
    const end = running ? now / 1000 : now / 1000;
    return formatDurationSec(Math.max(0, Math.round(end - instance.started_ts)), t);
  }, [instance, running, now, t]);

  const finalText = useMemo(() => {
    for (let i = steps.length - 1; i >= 0; i -= 1) {
      const kind = steps[i].kind;
      if (kind === 'llm' && steps[i].text) return steps[i].text;
    }
    return undefined;
  }, [steps]);

  return (
    <ModalOverlay open={open} onClose={onClose} className="chat-run-overlay">
      <div className="chat-run" role="dialog" aria-modal="true" aria-label={instance?.name}>
        <div className="chat-run__head">
          <span className="chat-run__name">{instance?.name}</span>
          {instance?.status ? <span className="chat-run__status">{instance.status}</span> : null}
          {instance && instance.started_ts > 0 ? (
            <span className="chat-run__elapsed">{elapsed}</span>
          ) : null}
          <button type="button" className="chat-run__close" onClick={onClose} aria-label="close">
            ✕
          </button>
        </div>
        {instance?.goal ? <p className="chat-run__goal">{instance.goal}</p> : null}
        <div className="chat-run__body">
          {steps.length === 0 && !hydrated ? (
            <p className="chat-run__empty">{t('chat:run.loading')}</p>
          ) : steps.length === 0 ? (
            <p className="chat-run__empty">{t('chat:run.empty')}</p>
          ) : (
            <ClosedTurnTrace steps={steps} finalText={finalText} />
          )}
        </div>
        {instance?.id ? (
          <div className="chat-run__foot">
            <span className="small muted">
              {t('chat:run.instanceId', { id: instance.id })}
              {runId ? ` · run ${runId}` : ''}
            </span>
            {running ? (
              <button
                type="button"
                className="chat-run__stop"
                onClick={() => void interruptInstance(instance.id)}
              >
                {t('chat:composer.stop')}
              </button>
            ) : null}
          </div>
        ) : null}
      </div>
    </ModalOverlay>
  );
}
