/**
 * @file ResumableList
 * @description Resumable/orphaned task list backed by list_resumable_checkpoints / resume_run / abandon_resumable_checkpoint; polls every 5s after mount.
 *
 * Entries with resumable=false (orphans) only offer "abandon". Task-type react
 * runs that crashed mid-turn show an "interrupted" hint. Follows the same pattern
 * as InstanceList: loads its own data, owns its state, reports its own toasts.
 *
 * Responsibilities:
 * - Poll resumable checkpoints every 5s and render entries with the
 *   interrupted hint for crashed react runs
 * - Resume or abandon entries, reloading immediately after the action
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { abandonResumableCheckpoint, listResumableCheckpoints, resumeRun } from '@/api/agent';
import { confirmDialog, useUIStore } from '@/stores/uiStore';
import { GlassCard } from '@/components/common/GlassCard';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState, EmptyStateIcons } from '@/components/common/EmptyState';
import { extractErrorMessage } from '@/utils/errors';
import { relativeTime, statusChipClass } from './instanceFormat';
import type { ResumableCheckpoint } from './types';

/** Poll interval for the resumable list; abandon/cancel reloads immediately instead of waiting for the next tick */
const POLL_MS = 5000;

/** Goal summary is truncated in the list; the full text lives in the title attribute */
function truncate(text: string, max = 80): string {
  return text.length > max ? `${text.slice(0, max)}…` : text;
}

export function ResumableList() {
  const { t } = useTranslation('team');
  const [items, setItems] = useState<ResumableCheckpoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyRunId, setBusyRunId] = useState<string | null>(null);
  const addToast = useUIStore((s) => s.addToast);

  const load = async () => {
    setLoading(true);
    setError(null);
    try {
      setItems(await listResumableCheckpoints<ResumableCheckpoint>());
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
      listResumableCheckpoints<ResumableCheckpoint>()
        .then((items) => {
          if (alive) setItems(items);
        })
        .catch(() => {});
    }, POLL_MS);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, []);

  const resume = async (item: ResumableCheckpoint) => {
    setBusyRunId(item.run_id);
    try {
      await resumeRun({
        run_id: item.run_id,
        continue_run: true,
      });
      addToast({
        type: 'success',
        message: t('team:resumable.toast.resumed', { name: item.instance_name }),
      });
      await load();
    } catch (err) {
      addToast({
        type: 'error',
        message: t('team:resumable.toast.resumeFailed', { message: extractErrorMessage(err) }),
      });
    } finally {
      setBusyRunId(null);
    }
  };

  const abandon = async (item: ResumableCheckpoint) => {
    if (
      !(await confirmDialog({
        message: t('team:resumable.confirm.abandon', { name: item.instance_name }),
        danger: true,
      }))
    ) {
      return;
    }
    setBusyRunId(item.run_id);
    try {
      await abandonResumableCheckpoint({
        run_id: item.run_id,
      });
      addToast({
        type: 'success',
        message: t('team:resumable.toast.abandoned', { name: item.instance_name }),
      });
      // Reload immediately after abandoning so the list does not wait for the next poll cycle
      await load();
    } catch (err) {
      addToast({
        type: 'error',
        message: t('team:resumable.toast.abandonFailed', { message: extractErrorMessage(err) }),
      });
    } finally {
      setBusyRunId(null);
    }
  };

  if (loading) {
    return (
      <section className="team-section">
        <h2 className="h3">{t('team:resumable.title')}</h2>
        <LoadingSpinner label={t('team:resumable.loading')} />
      </section>
    );
  }

  if (error) {
    return (
      <section className="team-section">
        <h2 className="h3">{t('team:resumable.title')}</h2>
        <EmptyState
          title={t('team:resumable.loadFailed')}
          description={error}
          icon={EmptyStateIcons.warning}
          onRetry={load}
        />
      </section>
    );
  }

  const recoverable = items.filter((i) => i.resumable !== false);
  const orphans = items.filter((i) => i.resumable === false);

  /** Row: recoverable entries show "resume + abandon"; orphans show "abandon" only */
  const row = (item: ResumableCheckpoint, orphan: boolean) => (
    <li key={item.run_id} className="inst-row">
      <div className="inst-row__head">
        <span className="inst-row__name">{item.instance_name}</span>
        <span className={`inst-row__status ${statusChipClass(item.status)}`}>{item.status}</span>
        {!orphan && (
          <button
            type="button"
            className="btn btn-sm btn-primary"
            disabled={busyRunId === item.run_id || item.status === 'running'}
            title={
              item.status === 'running'
                ? t('team:resumable.resumeTitleRunning')
                : t('team:resumable.resumeTitle', { name: item.instance_name })
            }
            onClick={() => void resume(item)}
          >
            {t('team:resumable.resume')}
          </button>
        )}
        <button
          type="button"
          className="btn btn-sm btn-danger"
          disabled={busyRunId === item.run_id}
          title={t('team:resumable.abandonTitle', { name: item.instance_name })}
          onClick={() => void abandon(item)}
        >
          {t('team:resumable.abandon')}
        </button>
      </div>
      <span className="inst-row__goal" title={item.goal}>
        {truncate(item.goal)}
      </span>
      {item.in_turn && (
        <span className="inst-row__step" title={t('team:resumable.interruptedTitle')}>
          {t('team:resumable.interrupted')}
        </span>
      )}
      {!item.in_turn && item.last_step && (
        <span className="inst-row__step" title={item.last_step}>
          {t('team:currentStep', { step: item.last_step })}
        </span>
      )}
      <span className="muted small">
        {item.run_id} · {relativeTime(item.started_ts)}
        {orphan ? ` · ${t('team:resumable.orphanHint')}` : ''}
      </span>
    </li>
  );

  return (
    <section className="team-section">
      <h2 className="h3">{t('team:resumable.title')}</h2>
      <GlassCard>
        {items.length === 0 ? (
          <EmptyState
            title={t('team:resumable.empty.title')}
            description={t('team:resumable.empty.description')}
            icon={EmptyStateIcons.team}
          />
        ) : (
          <>
            {recoverable.length > 0 && (
              <ul className="inst-list">{recoverable.map((i) => row(i, false))}</ul>
            )}
            {orphans.length > 0 && (
              <>
                <div className="muted small" style={{ margin: '10px 0 4px' }}>
                  {t('team:resumable.orphansSection')}
                </div>
                <ul className="inst-list">{orphans.map((i) => row(i, true))}</ul>
              </>
            )}
          </>
        )}
      </GlassCard>
    </section>
  );
}
