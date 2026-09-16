/**
 * @file SpawnToolFields
 * @description Tool-access section of the spawn form: unrestricted vs. whitelist selection.
 *
 * State is owned by SpawnForm; this component is purely presentational.
 *
 * Responsibilities:
 * - Render the unrestricted-vs-whitelist tool access choice
 * - Render the tool checkbox list and raise toggle changes to the form
 */

import { useTranslation } from 'react-i18next';
import type { ToolItem } from './types';

interface SpawnToolFieldsProps {
  toolMode: 'all' | 'custom';
  onToolMode: (mode: 'all' | 'custom') => void;
  tools: ToolItem[];
  pickedTools: string[];
  onToggleTool: (name: string) => void;
}

export function SpawnToolFields({
  toolMode,
  onToolMode,
  tools,
  pickedTools,
  onToggleTool,
}: SpawnToolFieldsProps) {
  const { t } = useTranslation('team');
  return (
    <div className="field-group">
      <span className="field-label">{t('team:spawnTools.label')}</span>
      <label className="spawn-form__tool">
        <input
          type="radio"
          name="spawn-tool-mode"
          checked={toolMode === 'all'}
          onChange={() => onToolMode('all')}
        />
        {t('team:tools.unrestricted')}
      </label>
      <label className="spawn-form__tool">
        <input
          type="radio"
          name="spawn-tool-mode"
          checked={toolMode === 'custom'}
          onChange={() => onToolMode('custom')}
        />
        {t('team:spawnTools.custom')}
      </label>
      {toolMode === 'custom' && (
        <div className="spawn-form__tools">
          {tools.map((tool) => (
            <label key={tool.name} className="spawn-form__tool" title={tool.description}>
              <input
                type="checkbox"
                checked={pickedTools.includes(tool.name)}
                onChange={() => onToggleTool(tool.name)}
              />
              <code className="mono">{tool.name}</code>
            </label>
          ))}
        </div>
      )}
      <span className="field-help">{t('team:spawnTools.help')}</span>
    </div>
  );
}
