/**
 * @file WorkspaceBlock
 * @description Settings block for the agent working directory (agent.workspace.dir), shared with the resource library.
 *
 * Responsibilities:
 * - Load and hot-switch agent.workspace.dir with validation
 * - Toast invalid input and switch outcomes
 *
 * Switching goes through POST /api/workspace/switch (validates, rebuilds
 * the agent without a service restart, persists the setting itself).
 * Backend access goes through the capability bridge and api helpers; no direct fetch.
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { switchWorkspace } from '@/api/workspace';
import { callCapability } from '@/bridge/client';
import { useUIStore } from '@/stores/uiStore';
import { extractErrorMessage } from '@/utils/errors';
import { WORKDIR_KEY } from './constants';
import type { SettingItem } from './types';

/** Working directory (agent.workspace.dir): relative to the repo root; saving hot-switches the agent, no restart needed */
export function WorkspaceBlock() {
  const { t } = useTranslation('settings');
  const addToast = useUIStore((s) => s.addToast);

  const [workdir, setWorkdir] = useState('');
  const [loadFailed, setLoadFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    callCapability<SettingItem<string>>('settings', 'get_setting', { key: WORKDIR_KEY })
      .then((item) => {
        if (alive) setWorkdir(item.value ?? item.default ?? '');
      })
      .catch(() => {
        if (alive) setLoadFailed(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  const saveWorkdir = () => {
    const next = workdir.trim();
    if (next.split(/[\\/]+/).includes('..')) {
      addToast({ type: 'warning', message: t('workspace.invalidPath') });
      return;
    }
    // Hot-switch rebuilds the agent (in-flight turns are drained); confirm
    // first since the switch interrupts running work.
    if (!window.confirm(t('workspace.switchConfirm'))) return;
    switchWorkspace(next)
      .then((res) => {
        setWorkdir(res.workspace);
        addToast({ type: 'success', message: t('workspace.switched') });
      })
      .catch((err) => {
        addToast({
          type: 'error',
          message: t('workspace.switchFailed', { message: extractErrorMessage(err) }),
        });
      });
  };

  return (
    <div className="agent-settings-block">
      <h3 className="agent-settings-subtitle">{t('workspace.title')}</h3>
      <p className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        {t('workspace.desc')}
      </p>
      {loadFailed ? (
        <p className="muted" style={{ fontSize: 12 }}>
          {t('common.loadFailed')}
        </p>
      ) : (
        <div className="memory-form-row">
          <input
            className="field input"
            style={{ maxWidth: 260 }}
            value={workdir}
            onChange={(e) => setWorkdir(e.target.value)}
            onBlur={saveWorkdir}
            placeholder="workspace"
            aria-label={t('workspace.title')}
          />
          <button type="button" className="btn btn-sm btn-ghost" onClick={saveWorkdir}>
            {t('common.save')}
          </button>
        </div>
      )}
    </div>
  );
}
