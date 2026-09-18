/**
 * @file SettingsToolbar
 * @description Shared toolbar for settings list sections: item count on the
 * left, search field and action buttons on the right (mirrors the reference
 * settings layout: "已安装 N 项 · 搜索框 · 刷新/新建").
 */

import type { ReactNode } from 'react';

interface SettingsToolbarProps {
  /** Left label, e.g. "已安装". */
  countLabel?: string;
  /** Item count rendered after the label. */
  count?: number;
  search: string;
  onSearch: (value: string) => void;
  searchPlaceholder: string;
  /** Right-aligned action buttons (refresh / create / ...). */
  actions?: ReactNode;
}

export function SettingsToolbar({
  countLabel,
  count,
  search,
  onSearch,
  searchPlaceholder,
  actions,
}: SettingsToolbarProps) {
  return (
    <div className="settings-toolbar">
      <div className="settings-toolbar__count">
        {countLabel}
        {typeof count === 'number' ? <span className="settings-toolbar__num">{count}</span> : null}
      </div>
      <div className="settings-toolbar__search">
        <svg
          viewBox="0 0 24 24"
          width="14"
          height="14"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          aria-hidden
        >
          <circle cx="11" cy="11" r="7" />
          <path d="M20 20l-3.5-3.5" />
        </svg>
        <input
          type="search"
          value={search}
          placeholder={searchPlaceholder}
          aria-label={searchPlaceholder}
          onChange={(e) => onSearch(e.target.value)}
        />
      </div>
      {actions ? <div className="settings-toolbar__actions">{actions}</div> : null}
    </div>
  );
}
