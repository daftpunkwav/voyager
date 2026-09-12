/**
 * @file ReadRootsBlock
 * @description Settings block for additional read-only filesystem roots (agent.fs.read_roots).
 *
 * Responsibilities:
 * - Edit agent.fs.read_roots as line-separated absolute paths
 * - Validate each path and save through the settings capability
 *
 * Backend access goes through the capability bridge and api helpers; no direct fetch.
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { callCapability } from '@/bridge/client';
import { useUIStore } from '@/stores/uiStore';
import { extractErrorMessage } from '@/utils/errors';
import { READ_ROOTS_KEY } from './constants';
import { isAbsolutePath } from './fsPathUtils';
import type { SettingItem } from './types';

/** Additional read-only roots (agent.fs.read_roots): read-only whitelist outside the working directory; takes effect at the next file-read check */
export function ReadRootsBlock() {
  const { t } = useTranslation('settings');
  const addToast = useUIStore((s) => s.addToast);

  const [rootsDraft, setRootsDraft] = useState('');
  const [loadFailed, setLoadFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    callCapability<SettingItem<string[]>>('settings', 'get_setting', { key: READ_ROOTS_KEY })
      .then((item) => {
        if (alive) setRootsDraft((item.value ?? item.default ?? []).join('\n'));
      })
      .catch(() => {
        if (alive) setLoadFailed(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  const saveRoots = () => {
    const lines = rootsDraft
      .split('\n')
      .map((s) => s.trim())
      .filter(Boolean);
    if (lines.length === 0) {
      callCapability<SettingItem<string[]>>('settings', 'set_setting', {
        key: READ_ROOTS_KEY,
        value: [],
      })
        .then(() => {
          setRootsDraft('');
          addToast({ type: 'success', message: t('readRoots.cleared') });
        })
        .catch((err) => {
          addToast({
            type: 'error',
            message: t('readRoots.saveFailed', { message: extractErrorMessage(err) }),
          });
        });
      return;
    }
    const bad = lines.find((line) => !isAbsolutePath(line) || line.split(/[\\/]+/).includes('..'));
    if (bad) {
      addToast({
        type: 'warning',
        message: t('fsroots.invalidPath', { line: bad }),
      });
      return;
    }
    callCapability<SettingItem<string[]>>('settings', 'set_setting', {
      key: READ_ROOTS_KEY,
      value: lines,
    })
      .then(() => {
        setRootsDraft(lines.join('\n'));
        addToast({ type: 'success', message: t('readRoots.saved') });
      })
      .catch((err) => {
        addToast({
          type: 'error',
          message: t('readRoots.saveFailed', { message: extractErrorMessage(err) }),
        });
      });
  };

  return (
    <div className="agent-settings-block">
      <h3 className="agent-settings-subtitle">{t('readRoots.title')}</h3>
      <p className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        {t('readRoots.desc')}
      </p>
      {loadFailed ? (
        <p className="muted" style={{ fontSize: 12 }}>
          {t('common.loadFailed')}
        </p>
      ) : (
        <>
          <textarea
            className="field input agent-guideline-textarea"
            rows={3}
            value={rootsDraft}
            onChange={(e) => setRootsDraft(e.target.value)}
            onBlur={saveRoots}
            placeholder={'D:\\docs\n/home/me/docs'}
            aria-label={t('readRoots.title')}
          />
          <div className="agent-guideline-meta">
            <span className="muted">
              {t('fsroots.dirCount', {
                count: rootsDraft.split('\n').filter((s) => s.trim()).length,
              })}
            </span>
            <button type="button" className="btn btn-sm btn-ghost" onClick={saveRoots}>
              {t('common.save')}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
