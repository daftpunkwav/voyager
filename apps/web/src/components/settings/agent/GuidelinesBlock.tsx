/**
 * @file GuidelinesBlock
 * @description Settings block for per-agent conduct rules (agent.guidelines), layered on top of the global rules.
 *
 * Responsibilities:
 * - Edit per-agent guideline texts in tabs over the shared agent.guidelines map
 * - Merge the active tab on save; an emptied text deletes its key
 *
 * Backend access goes through the capability bridge and api helpers; no direct fetch.
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { callCapability } from '@/bridge/client';
import { AGENT_CATALOG } from '@/constants/agentCatalog';
import { useUIStore } from '@/stores/uiStore';
import { extractErrorMessage } from '@/utils/errors';
import { DEFAULT_AGENT_ID, GUIDELINES_KEY, GUIDELINE_MAX } from './constants';
import type { SettingItem } from './types';

/** Per-agent conduct rules (agent.guidelines): value is { <persona struct id>: text }; saving merges the active tab, empty string deletes the key */
export function GuidelinesBlock() {
  const { t } = useTranslation('settings');
  const addToast = useUIStore((s) => s.addToast);
  const [activeAgentId, setActiveAgentId] = useState(DEFAULT_AGENT_ID);
  const [guidelineDrafts, setGuidelineDrafts] = useState<Record<string, string>>(() => {
    const map: Record<string, string> = {};
    for (const a of AGENT_CATALOG) map[a.id] = '';
    return map;
  });
  const [saved, setSaved] = useState<Record<string, string> | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    callCapability<SettingItem<Record<string, string>>>('settings', 'get_setting', {
      key: GUIDELINES_KEY,
    })
      .then((item) => {
        if (!alive) return;
        const raw = item.value ?? item.default ?? {};
        const map: Record<string, string> = {};
        for (const a of AGENT_CATALOG) map[a.id] = typeof raw[a.id] === 'string' ? raw[a.id] : '';
        setGuidelineDrafts(map);
        setSaved(raw);
      })
      .catch(() => {
        if (alive) setLoadFailed(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  const saveGuideline = (agentId: string) => {
    if (saved === null) return;
    const text = (guidelineDrafts[agentId] ?? '').slice(0, GUIDELINE_MAX);
    if (text === (saved[agentId] ?? '')) return;
    // merge: update only the active tab's persona id; empty string deletes the key; other keys (including unknown/custom ones) are preserved as-is
    const next = { ...saved };
    if (text) next[agentId] = text;
    else delete next[agentId];
    callCapability<SettingItem<Record<string, string>>>('settings', 'set_setting', {
      key: GUIDELINES_KEY,
      value: next,
    })
      .then(() => {
        setSaved(next);
        addToast({
          type: 'success',
          message: t('guidelines.saved', {
            name: AGENT_CATALOG.find((a) => a.id === agentId)?.name ?? agentId,
          }),
        });
      })
      .catch((err) => {
        const name = AGENT_CATALOG.find((a) => a.id === agentId)?.name ?? agentId;
        addToast({
          type: 'error',
          message: t('guidelines.saveFailed', { name, message: extractErrorMessage(err) }),
        });
      });
  };

  const activeAgent = AGENT_CATALOG.find((a) => a.id === activeAgentId) ?? AGENT_CATALOG[0];

  return (
    <div className="agent-settings-block">
      <h3 className="agent-settings-subtitle">{t('guidelines.title')}</h3>
      <p className="muted" style={{ fontSize: 12, marginBottom: 10 }}>
        {t('guidelines.desc')}
      </p>
      {loadFailed ? (
        <p className="muted" style={{ fontSize: 12 }}>
          {t('common.loadFailed')}
        </p>
      ) : (
        <>
          <div
            className="agent-guideline-tabs"
            role="tablist"
            aria-label={t('guidelines.tabsAria')}
          >
            {AGENT_CATALOG.map((a) => (
              <button
                key={a.id}
                type="button"
                role="tab"
                aria-selected={a.id === activeAgentId}
                className={`agent-guideline-tab ${a.id === activeAgentId ? 'active' : ''}`}
                onClick={() => setActiveAgentId(a.id)}
              >
                {a.name}
              </button>
            ))}
          </div>
          {activeAgent && (
            <div className="agent-guideline-panel">
              <div className="agent-guideline-panel__head">
                <strong>{activeAgent.name}</strong>
                <span className="muted">{activeAgent.tagline}</span>
              </div>
              <textarea
                className="field input agent-guideline-textarea"
                rows={4}
                maxLength={GUIDELINE_MAX}
                value={guidelineDrafts[activeAgent.id] ?? ''}
                onChange={(e) =>
                  setGuidelineDrafts((prev) => ({ ...prev, [activeAgent.id]: e.target.value }))
                }
                onBlur={() => saveGuideline(activeAgent.id)}
                placeholder={t('guidelines.placeholder', { name: activeAgent.name })}
                aria-label={t('guidelines.textareaAria', { name: activeAgent.name })}
              />
              <div className="agent-guideline-meta">
                <span className="muted">
                  {(guidelineDrafts[activeAgent.id] ?? '').length}/{GUIDELINE_MAX}
                </span>
                <button
                  type="button"
                  className="btn btn-sm btn-ghost"
                  onClick={() => saveGuideline(activeAgent.id)}
                >
                  {t('common.save')}
                </button>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  );
}
