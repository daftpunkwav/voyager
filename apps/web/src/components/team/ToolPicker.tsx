/**
 * @file ToolPicker
 * @description Categorized tool whitelist picker: the roster grouped by domain
 * prefix / dimension, with a per-group select-all so a whole category (e.g.
 * all notes tools) can be granted in one click.
 *
 * Purely presentational: picked names and toggle callbacks are owned by the
 * consumer (SubagentDialog).
 */

import { useTranslation } from 'react-i18next';
import { groupTools, toolGroupLabel } from './toolGroups';
import type { ToolItem } from './types';

interface ToolPickerProps {
  tools: ToolItem[];
  pickedTools: string[];
  onToggleTool: (name: string) => void;
  /** Select/deselect an entire group at once. */
  onToggleGroup: (names: string[], picked: boolean) => void;
}

export function ToolPicker({ tools, pickedTools, onToggleTool, onToggleGroup }: ToolPickerProps) {
  const { t } = useTranslation('team');
  const groups = groupTools(tools);

  return (
    <div className="tool-picker">
      {groups.map((group) => {
        const names = group.tools.map((tool) => tool.name);
        const pickedCount = names.filter((name) => pickedTools.includes(name)).length;
        const allPicked = pickedCount === names.length;
        return (
          <div key={group.key} className="tool-picker__group">
            <label className="tool-picker__group-head">
              <input
                type="checkbox"
                checked={allPicked}
                onChange={() => onToggleGroup(names, !allPicked)}
                aria-label={t('team:toolPicker.toggleGroup', {
                  group: toolGroupLabel(t, group.key),
                })}
              />
              <span className="tool-picker__group-name">{toolGroupLabel(t, group.key)}</span>
              <span className="tool-picker__group-count">
                {t('team:toolPicker.groupCount', { picked: pickedCount, total: names.length })}
              </span>
            </label>
            <div className="tool-picker__items">
              {group.tools.map((tool) => (
                <label key={tool.name} className="tool-picker__item" title={tool.description}>
                  <input
                    type="checkbox"
                    checked={pickedTools.includes(tool.name)}
                    onChange={() => onToggleTool(tool.name)}
                    aria-label={tool.name}
                  />
                  <code className="mono">{tool.name}</code>
                  {tool.write ? (
                    <span className="tool-picker__write">{t('team:toolPicker.write')}</span>
                  ) : null}
                </label>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}
