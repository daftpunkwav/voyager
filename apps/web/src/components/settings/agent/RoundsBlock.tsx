/**
 * @file RoundsBlock
 * @description Settings block for conversation round limits (agent.rounds.*): global caps on ReAct reasoning turns and tool calls.
 *
 * Responsibilities:
 * - Load and save the agent.rounds.* caps on reasoning turns and tool calls
 * - Validate ranges and toast invalid input or save outcomes
 *
 * Backend access goes through the capability bridge and api helpers; no direct fetch.
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { callCapability } from '@/bridge/client';
import { useUIStore } from '@/stores/uiStore';
import { extractErrorMessage } from '@/utils/errors';
import {
  numericDraft,
  ROUNDS_MAX_KEY,
  ROUNDS_RE_MAX,
  ROUNDS_TOOL_KEY,
  ROUNDS_TOOL_MAX,
} from './constants';
import type { SettingItem } from './types';

/** Round limits (agent.rounds.*): global caps on ReAct reasoning turns and tool call counts */
export function RoundsBlock() {
  const { t } = useTranslation('settings');
  const addToast = useUIStore((s) => s.addToast);

  const [roundsRe, setRoundsRe] = useState('');
  const [roundsTool, setRoundsTool] = useState('');
  const [loadFailed, setLoadFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    callCapability<SettingItem<number>>('settings', 'get_setting', { key: ROUNDS_MAX_KEY })
      .then((item) => {
        if (alive) setRoundsRe(numericDraft(item));
      })
      .catch(() => {
        if (alive) setLoadFailed(true);
      });
    callCapability<SettingItem<number>>('settings', 'get_setting', { key: ROUNDS_TOOL_KEY })
      .then((item) => {
        if (alive) setRoundsTool(numericDraft(item));
      })
      .catch(() => {
        if (alive) setLoadFailed(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  const saveRound = (key: string, draft: string, max: number, label: string) => {
    const n = Number(draft);
    if (!Number.isInteger(n) || n < 1 || n > max) {
      addToast({ type: 'warning', message: t('rounds.invalidRange', { label, max }) });
      return;
    }
    callCapability<SettingItem<number>>('settings', 'set_setting', { key, value: n })
      .then(() => {
        addToast({ type: 'success', message: t('rounds.saved', { label }) });
      })
      .catch((err) => {
        addToast({
          type: 'error',
          message: t('rounds.saveFailed', { label, message: extractErrorMessage(err) }),
        });
      });
  };

  return (
    <div className="agent-settings-block">
      <h3 className="agent-settings-subtitle">{t('rounds.title')}</h3>
      <p className="muted" style={{ fontSize: 12, marginBottom: 8 }}>
        {t('rounds.desc')}
      </p>
      {loadFailed ? (
        <p className="muted" style={{ fontSize: 12 }}>
          {t('common.loadFailed')}
        </p>
      ) : (
        <>
          <div className="memory-form-row">
            <span className="muted" style={{ fontSize: 12 }}>
              {t('rounds.reLabel')}
            </span>
            <input
              className="field input"
              type="number"
              min={1}
              max={ROUNDS_RE_MAX}
              style={{ maxWidth: 120 }}
              value={roundsRe}
              onChange={(e) => setRoundsRe(e.target.value)}
              onBlur={() => saveRound(ROUNDS_MAX_KEY, roundsRe, ROUNDS_RE_MAX, t('rounds.reLabel'))}
              aria-label={t('rounds.reAria')}
            />
            <button
              type="button"
              className="btn btn-sm btn-ghost"
              onClick={() =>
                saveRound(ROUNDS_MAX_KEY, roundsRe, ROUNDS_RE_MAX, t('rounds.reLabel'))
              }
            >
              {t('common.save')}
            </button>
          </div>
          <div className="memory-form-row">
            <span className="muted" style={{ fontSize: 12 }}>
              {t('rounds.toolLabel')}
            </span>
            <input
              className="field input"
              type="number"
              min={1}
              max={ROUNDS_TOOL_MAX}
              style={{ maxWidth: 120 }}
              value={roundsTool}
              onChange={(e) => setRoundsTool(e.target.value)}
              onBlur={() =>
                saveRound(ROUNDS_TOOL_KEY, roundsTool, ROUNDS_TOOL_MAX, t('rounds.toolLabel'))
              }
              aria-label={t('rounds.toolAria')}
            />
            <button
              type="button"
              className="btn btn-sm btn-ghost"
              onClick={() =>
                saveRound(ROUNDS_TOOL_KEY, roundsTool, ROUNDS_TOOL_MAX, t('rounds.toolLabel'))
              }
            >
              {t('common.save')}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
