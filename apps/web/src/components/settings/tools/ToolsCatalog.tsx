/**
 * @file ToolsCatalog
 * @description Settings "工具" section: the agent tool roster grouped by
 * category (domain prefix / dimension) with search, category filter chips,
 * write badges, and a lazy per-tool detail expand (describe_tool) that shows
 * the full description and the parameter schema.
 */

import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { describeTool, listTools } from '@/api/agent';
import { useUIStore } from '@/stores/uiStore';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { EmptyState, EmptyStateIcons } from '@/components/common/EmptyState';
import { SettingsToolbar } from '@/components/settings/SettingsToolbar';
import { extractErrorMessage } from '@/utils/errors';
import { groupTools, toolGroupLabel, toolGroupKey } from '@/components/team/toolGroups';
import type { ToolDetail, ToolItem } from '@/components/team/types';

export function ToolsCatalog() {
  const { t } = useTranslation('settings');
  const addToast = useUIStore((s) => s.addToast);
  const [tools, setTools] = useState<ToolItem[] | null>(null);
  const [loadError, setLoadError] = useState('');
  const [search, setSearch] = useState('');
  const [category, setCategory] = useState('');
  const [expanded, setExpanded] = useState<string | null>(null);
  const [details, setDetails] = useState<Record<string, ToolDetail | 'loading'>>({});

  useEffect(() => {
    let alive = true;
    listTools<ToolItem>()
      .then((items) => {
        if (alive) setTools(Array.isArray(items) ? items : []);
      })
      .catch((err) => {
        if (alive) setLoadError(extractErrorMessage(err));
      });
    return () => {
      alive = false;
    };
  }, []);

  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    return (tools ?? []).filter((tool) => {
      if (category && toolGroupKey(tool) !== category) return false;
      if (!q) return true;
      return (
        tool.name.toLowerCase().includes(q) ||
        (tool.description ?? '').toLowerCase().includes(q)
      );
    });
  }, [tools, search, category]);

  const groups = useMemo(() => groupTools(filtered), [filtered]);
  const allGroups = useMemo(() => groupTools(tools ?? []), [tools]);

  const toggleRow = (name: string) => {
    if (expanded === name) {
      setExpanded(null);
      return;
    }
    setExpanded(name);
    // Lazy detail: the parameter schema rides describe_tool, fetched once per tool.
    if (details[name] === undefined) {
      setDetails((prev) => ({ ...prev, [name]: 'loading' }));
      describeTool<ToolDetail>(name)
        .then((info) => setDetails((prev) => ({ ...prev, [name]: info })))
        .catch((err) => {
          setDetails((prev) => {
            const next = { ...prev };
            delete next[name];
            return next;
          });
          addToast({
            type: 'error',
            message: t('tools.detailFailed', { message: extractErrorMessage(err) }),
          });
        });
    }
  };

  if (tools === null && !loadError) {
    return <LoadingSpinner label={t('tools.loading')} />;
  }
  if (loadError) {
    return (
      <EmptyState
        title={t('tools.loadFailed')}
        description={loadError}
        icon={EmptyStateIcons.warning}
        onRetry={() => {
          setLoadError('');
          listTools<ToolItem>()
            .then((items) => setTools(Array.isArray(items) ? items : []))
            .catch((err) => setLoadError(extractErrorMessage(err)));
        }}
      />
    );
  }

  return (
    <div className="tools-catalog">
      <SettingsToolbar
        countLabel={t('tools.countLabel')}
        count={filtered.length}
        search={search}
        onSearch={setSearch}
        searchPlaceholder={t('tools.searchPlaceholder')}
      />

      {allGroups.length > 0 && (
        <div className="chips tools-catalog__filters">
          <button
            type="button"
            className={`chip${category === '' ? ' active' : ''}`}
            onClick={() => setCategory('')}
          >
            {t('tools.filterAll')}
          </button>
          {allGroups.map((group) => (
            <button
              key={group.key}
              type="button"
              className={`chip${category === group.key ? ' active' : ''}`}
              aria-label={`${toolGroupLabel(t, group.key)} ${group.tools.length}`}
              onClick={() => setCategory(category === group.key ? '' : group.key)}
            >
              {toolGroupLabel(t, group.key)}
              <span className="tools-catalog__chip-count">{group.tools.length}</span>
            </button>
          ))}
        </div>
      )}

      {filtered.length === 0 ? (
        <p className="muted small">{t('tools.searchEmpty')}</p>
      ) : (
        groups.map((group) => (
          <section key={group.key} className="tools-catalog__group">
            <div className="settings-group-label">
              {toolGroupLabel(t, group.key)}
              <span className="tools-catalog__group-count">
                {t('tools.groupCount', { n: group.tools.length })}
              </span>
            </div>
            <ul className="settings-rows">
              {group.tools.map((tool) => {
                const open = expanded === tool.name;
                const detail = details[tool.name];
                return (
                  <li key={tool.name} className={`settings-row entity-row${open ? ' is-open' : ''}`}>
                    <button
                      type="button"
                      className="entity-row__main entity-row__open"
                      aria-expanded={open}
                      onClick={() => toggleRow(tool.name)}
                    >
                      <span className="entity-row__title">
                        <code className="mono entity-row__name">{tool.name}</code>
                        {tool.write ? (
                          <span className="chip chip--danger">{t('tools.writeBadge')}</span>
                        ) : null}
                      </span>
                      {tool.description && (
                        <span className="entity-row__desc">{tool.description}</span>
                      )}
                      {open && (
                        <span className="tools-catalog__detail">
                          {detail === 'loading' || detail === undefined ? (
                            <span className="muted small">{t('tools.detailLoading')}</span>
                          ) : (
                            <>
                              <span className="tools-catalog__detail-label">
                                {t('tools.parameters')}
                              </span>
                              {detail.parameters?.properties &&
                              Object.keys(detail.parameters.properties).length > 0 ? (
                                <ul className="tools-catalog__params">
                                  {Object.entries(detail.parameters.properties).map(
                                    ([paramName, schema]) => {
                                      const required =
                                        detail.parameters.required?.includes(paramName) ?? false;
                                      return (
                                        <li key={paramName} className="tools-catalog__param">
                                          <code className="mono">{paramName}</code>
                                          <span className="tools-catalog__param-type">
                                            {schema?.type ?? 'any'}
                                            {required ? (
                                              <em className="tools-catalog__param-required">
                                                {t('tools.paramRequired')}
                                              </em>
                                            ) : null}
                                          </span>
                                          {schema?.description ? (
                                            <span className="tools-catalog__param-desc">
                                              {schema.description}
                                            </span>
                                          ) : null}
                                        </li>
                                      );
                                    }
                                  )}
                                </ul>
                              ) : (
                                <span className="muted small">{t('tools.noParams')}</span>
                              )}
                            </>
                          )}
                        </span>
                      )}
                    </button>
                  </li>
                );
              })}
            </ul>
          </section>
        ))
      )}
    </div>
  );
}
