/**
 * @file SkillsBlock
 * @description Settings "技能" section in the reference layout: toolbar (count
 * + search) above a row list of skill entries with a clamped description.
 * Read-only: the index lives in conversation context, this view only displays
 * it.
 */

import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { listSkills } from '@/api/agent';
import { EmptyState, EmptyStateIcons } from '@/components/common/EmptyState';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { SettingsToolbar } from '@/components/settings/SettingsToolbar';
import type { SkillItem } from './types';

export function SkillsBlock() {
  const { t } = useTranslation('settings');
  const [skills, setSkills] = useState<SkillItem[] | null>(null);
  const [skillsLoadFailed, setSkillsLoadFailed] = useState(false);
  const [search, setSearch] = useState('');

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

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return skills ?? [];
    return (skills ?? []).filter(
      (s) => s.name.toLowerCase().includes(q) || (s.description ?? '').toLowerCase().includes(q)
    );
  }, [skills, search]);

  if (skillsLoadFailed) {
    return (
      <EmptyState
        title={t('skills.loadFailedTitle')}
        description={t('common.loadFailed')}
        icon={EmptyStateIcons.warning}
        onRetry={() => {
          setSkillsLoadFailed(false);
          listSkills<SkillItem>()
            .then((items) => setSkills(Array.isArray(items) ? items : []))
            .catch(() => setSkillsLoadFailed(true));
        }}
      />
    );
  }
  if (skills === null) {
    return <LoadingSpinner label={t('skills.loading')} />;
  }

  return (
    <div className="skills-block">
      <SettingsToolbar
        countLabel={t('skills.installed')}
        count={filtered.length}
        search={search}
        onSearch={setSearch}
        searchPlaceholder={t('skills.searchPlaceholder')}
      />
      {filtered.length === 0 ? (
        skills.length === 0 ? (
          <EmptyState
            title={t('skills.emptyTitle')}
            description={t('skills.empty')}
            icon={EmptyStateIcons.team}
          />
        ) : (
          <p className="muted small">{t('skills.searchEmpty')}</p>
        )
      ) : (
        <ul className="settings-rows">
          {filtered.map((s) => (
            <li key={s.name} className="settings-row entity-row">
              <span className="entity-icon entity-icon--spark" aria-hidden>
                <svg
                  viewBox="0 0 24 24"
                  width="16"
                  height="16"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="1.8"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  <path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z" />
                  <path d="M19 15l.9 2.6L22.5 18.5l-2.6.9L19 22l-.9-2.6-2.6-.9 2.6-.9z" />
                </svg>
              </span>
              <div className="entity-row__main">
                <span className="entity-row__title">
                  <span className="entity-row__name mono">{s.name}</span>
                </span>
                {s.description && <span className="entity-row__desc">{s.description}</span>}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
