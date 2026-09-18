/**
 * @file InstanceList
 * @description Running subagent instance list; loads list_subagents.running, polls every 5s after mount, and offers emergency-stop.
 *
 * Responsibilities:
 * - Load and poll running instances, rendering status chips and relative
 *   start times
 * - Emergency-stop a run via cancel_run and mark the chat timeline
 *   interrupted
 * - Patch the running count into the team snapshot
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ServiceError } from '@/bridge/client';
import { cancelRun, listSubagents } from '@/api/agent';
import { markChatInterrupted } from '@/bridge/chatSend';
import { useUIStore } from '@/stores/uiStore';
import { GlassCard } from '@/components/common/GlassCard';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState, EmptyStateIcons } from '@/components/common/EmptyState';
import { extractErrorMessage } from '@/utils/errors';
import { patchTeamSnapshot } from './provider';
import { relativeTime, statusChipClass } from './instanceFormat';
import type { RunningSubagent } from './types';

export function InstanceList() {
  const { t } = useTranslation('team');
  const [instances, setInstances] = useState<RunningSubagent[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const addToast = useUIStore((s) => s.addToast);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      const s = await listSubagents();
      // Conversational entries are the chat sessions themselves (the user
      // talking to Lucien), not dispatched subagents: keep them out of the
      // subagent roster; the chat page's own panel labels them instead.
      const runningArr = ((s.running as RunningSubagent[]) ?? []).filter(
        (r) => r.conversational !== true
      );
      setInstances(runningArr);
      patchTeamSnapshot({ running: runningArr.filter((r) => r.status === 'running').length });
    } catch (err) {
      setError(extractErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  useEffect(() => {
    let alive = true;
    const timer = setInterval(() => {
      listSubagents()
        .then((s) => {
          if (!alive) return;
          const runningArr = ((s.running as RunningSubagent[]) ?? []).filter(
            (r) => r.conversational !== true
          );
          setInstances(runningArr);
          patchTeamSnapshot({ running: runningArr.filter((r) => r.status === 'running').length });
        })
        .catch(() => {});
    }, 5000);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);

  const stopRun = async (r: RunningSubagent) => {
    const isChat = r.id === 'chat' || r.name === 'chat';
    try {
      await cancelRun(r.id);
      if (isChat) markChatInterrupted();
      addToast({
        type: 'success',
        message: isChat
          ? t('team:inst.toast.interruptedChat')
          : t('team:inst.toast.interrupted', { name: r.name }),
      });
      setInstances((prev) => prev.filter((x) => x.id !== r.id && x.name !== r.id));
    } catch (err) {
      const notFound = err instanceof ServiceError && err.code.includes('NOT_FOUND');
      if (notFound) {
        setInstances((prev) => prev.filter((x) => x.id !== r.id && x.name !== r.id));
      }
      addToast({
        type: 'error',
        message: notFound
          ? t('team:inst.toast.notRunning', { name: r.name })
          : t('team:inst.toast.stopFailed', { message: extractErrorMessage(err) }),
      });
    }
  };

  if (loading) {
    return (
      <section className="team-section">
        <h2 className="h3">{t('team:inst.title')}</h2>
        <LoadingSpinner label={t('team:inst.loading')} />
      </section>
    );
  }

  if (error) {
    return (
      <section className="team-section">
        <h2 className="h3">{t('team:inst.title')}</h2>
        <EmptyState
          title={t('team:inst.loadFailed')}
          description={error}
          icon={EmptyStateIcons.warning}
          onRetry={load}
        />
      </section>
    );
  }

  return (
    <section className="team-section">
      <h2 className="h3">{t('team:inst.title')}</h2>
      <GlassCard>
        {instances.length === 0 ? (
          <EmptyState
            title={t('team:inst.empty.title')}
            description={t('team:inst.empty.description')}
            icon={EmptyStateIcons.team}
          />
        ) : (
          <ul className="inst-list">
            {instances.map((r) => (
              <li key={r.id} className="inst-row">
                <div className="inst-row__head">
                  <span className="inst-row__name">{r.name}</span>
                  <span className={`inst-row__status ${statusChipClass(r.status)}`}>
                    {r.status}
                  </span>
                  {r.status === 'running' && (
                    <button
                      type="button"
                      className="btn btn-sm btn-danger"
                      title={
                        r.name === 'chat'
                          ? t('team:inst.stopTitleChat')
                          : t('team:inst.stopTitle', { name: r.name })
                      }
                      onClick={() => void stopRun(r)}
                    >
                      {t('team:inst.stop')}
                    </button>
                  )}
                </div>
                <span className="inst-row__goal">{r.goal}</span>
                {r.last_step && (
                  <span className="inst-row__step" title={r.last_step}>
                    {t('team:currentStep', { step: r.last_step })}
                  </span>
                )}
                <span className="muted small">
                  {r.id} · {relativeTime(r.started_ts)}
                  {r.name === 'chat' || r.id === 'chat' ? ` · ${t('team:inst.chatNote')}` : ''}
                </span>
              </li>
            ))}
          </ul>
        )}
      </GlassCard>
    </section>
  );
}
