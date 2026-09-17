/**
 * @file SkillsBlock
 * @description Read-only listing of agent skills; the index lives in conversation context, this view only displays it.
 *
 * Responsibilities:
 * - Load the skill inventory once and list it read-only
 * - Distinguish load failure from the empty inventory
 *
 * Backend access goes through the capability bridge and api helpers; no direct fetch.
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { listSkills } from '@/api/agent';
import type { SkillItem } from './types';

/** Skill inventory (read-only): the index stays resident in conversation context; this only displays it */
export function SkillsBlock() {
  const { t } = useTranslation('settings');
  const [skills, setSkills] = useState<SkillItem[] | null>(null);
  const [skillsLoadFailed, setSkillsLoadFailed] = useState(false);

  useEffect(() => {
    let alive = true;
    listSkills<SkillItem>()
      .then((items) => {
        if (alive) setSkills(Array.isArray(items) ? items : []);
      })
      .catch(() => {
        if (alive) setSkillsLoadFailed(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  return (
    <div className="agent-settings-block">
      <h3 className="agent-settings-subtitle">{t('skills.title')}</h3>
      {skillsLoadFailed ? (
        <p className="muted" style={{ fontSize: 12 }}>
          {t('common.loadFailed')}
        </p>
      ) : skills === null ? (
        <p className="muted" style={{ fontSize: 12 }}>
          {t('skills.loading')}
        </p>
      ) : skills.length === 0 ? (
        <p className="muted" style={{ fontSize: 12 }}>
          {t('skills.empty')}
        </p>
      ) : (
        <ul className="memory-entry-list">
          {skills.map((s) => (
            <li key={s.name} className="memory-entry">
              <span className="memory-kind">{s.name}</span>
              <span className="memory-entry-summary">{s.description}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
