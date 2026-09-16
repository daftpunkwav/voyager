/**
 * @file SpawnForm
 * @description Spawn form for registering custom subagents, with overwrite confirmation for duplicate names.
 *
 * Loads its own data (list_personas for the dropdown, list_tools for the whitelist,
 * list_subagents for duplicate checks) and notifies DefinitionGrid via defsEvents
 * after a successful registration.
 *
 * Responsibilities:
 * - Collect the spawn fields: name (client-side regex first), description,
 *   execution mode, persona, tool whitelist, round limits, network tier
 * - Confirm overwriting an existing definition with the same name
 * - Register via register_subagent and notify DefinitionGrid through
 *   defsEvents
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { listPersonas, listSubagents, listTools, registerSubagent } from '@/api/agent';
import { useUIStore } from '@/stores/uiStore';
import { GlassCard } from '@/components/common/GlassCard';
import { GlassSelect } from '@/components/common/GlassSelect';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { extractErrorMessage } from '@/utils/errors';
import { notifyTeamDefsChanged } from './defsEvents';
import { patchTeamSnapshot } from './provider';
import { NAME_RE, MODE_OPTIONS, NETWORK_OPTIONS } from './constants';
import { SpawnToolFields } from './SpawnToolFields';
import type { PersonaItem, SubagentDef, ToolItem } from './types';

export function SpawnForm() {
  const { t } = useTranslation('team');
  const [personas, setPersonas] = useState<PersonaItem[]>([]);
  const [tools, setTools] = useState<ToolItem[]>([]);
  const [definitions, setDefinitions] = useState<SubagentDef[]>([]);
  const [dataLoading, setDataLoading] = useState(true);

  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [mode, setMode] = useState('react');
  const [persona, setPersona] = useState('');
  const [toolMode, setToolMode] = useState<'all' | 'custom'>('all');
  const [pickedTools, setPickedTools] = useState<string[]>([]);
  const [maxRounds, setMaxRounds] = useState('');
  const [maxToolRounds, setMaxToolRounds] = useState('');
  const [networkMode, setNetworkMode] = useState('');

  const [confirmOverwrite, setConfirmOverwrite] = useState(false);
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState('');

  const addToast = useUIStore((s) => s.addToast);

  useEffect(() => {
    let alive = true;
    (async () => {
      setDataLoading(true);
      try {
        const [personasArr, toolsArr, sub] = await Promise.all([
          listPersonas<PersonaItem>(),
          listTools<ToolItem>(),
          listSubagents(),
        ]);
        if (!alive) return;
        const defsArr = (sub.definitions as SubagentDef[]) ?? [];
        setPersonas(personasArr);
        setTools(toolsArr);
        setDefinitions(defsArr);
      } catch (err) {
        if (alive)
          addToast({
            type: 'error',
            message: t('team:spawn.toast.loadFailed', { message: extractErrorMessage(err) }),
          });
      } finally {
        if (alive) setDataLoading(false);
      }
    })();
    return () => {
      alive = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- fetch on mount only; t only composes the toast copy, so adding it would refetch the form data on every language switch
  }, [addToast]);

  const toggleTool = (toolName: string) => {
    setPickedTools((prev) =>
      prev.includes(toolName) ? prev.filter((n) => n !== toolName) : [...prev, toolName]
    );
  };

  const parseRounds = (draft: string): number | null => {
    const trimmed = draft.trim();
    if (trimmed === '') return null;
    const n = Number(trimmed);
    if (!Number.isInteger(n) || n < 1) return NaN;
    return n;
  };

  const resetForm = () => {
    setName('');
    setDescription('');
    setMode('react');
    setPersona('');
    setToolMode('all');
    setPickedTools([]);
    setMaxRounds('');
    setMaxToolRounds('');
    setNetworkMode('');
  };

  const doRegister = async () => {
    setBusy(true);
    setFormError('');
    try {
      const args: Record<string, unknown> = {
        name: name.trim(),
        description: description.trim(),
        mode,
        persona,
      };
      if (toolMode === 'custom') args.allowed_tools = pickedTools;
      if (maxRounds.trim() !== '') args.max_rounds = Number(maxRounds);
      if (maxToolRounds.trim() !== '') args.max_tool_calls = Number(maxToolRounds);
      if (networkMode) args.network_mode = networkMode;
      await registerSubagent(args);
      addToast({
        type: 'success',
        message: t('team:spawn.toast.registered', { name: name.trim() }),
      });

      const s = await listSubagents();
      const defsArr = (s.definitions as SubagentDef[]) ?? [];
      setDefinitions(defsArr);
      patchTeamSnapshot({ definitions: defsArr.length });
      notifyTeamDefsChanged();
      resetForm();
    } catch (err) {
      addToast({
        type: 'error',
        message: t('team:spawn.toast.failed', { message: extractErrorMessage(err) }),
      });
    } finally {
      setBusy(false);
    }
  };

  const submit = () => {
    const trimmedName = name.trim();
    if (!NAME_RE.test(trimmedName)) {
      setFormError(t('team:spawn.error.name'));
      return;
    }
    if (!description.trim()) {
      setFormError(t('team:spawn.error.description'));
      return;
    }
    if (toolMode === 'custom' && pickedTools.length === 0) {
      setFormError(t('team:spawn.error.tools'));
      return;
    }
    if (Number.isNaN(parseRounds(maxRounds))) {
      setFormError(t('team:spawn.error.maxRounds'));
      return;
    }
    if (Number.isNaN(parseRounds(maxToolRounds))) {
      setFormError(t('team:spawn.error.maxToolRounds'));
      return;
    }
    setFormError('');
    if (definitions.some((d) => d.name === trimmedName)) {
      setConfirmOverwrite(true);
      return;
    }
    void doRegister();
  };

  if (dataLoading) {
    return (
      <section className="team-section">
        <h2 className="h3">{t('team:spawn.title')}</h2>
        <LoadingSpinner label={t('team:spawn.loading')} />
      </section>
    );
  }

  return (
    <>
      <section className="team-section">
        <h2 className="h3">{t('team:spawn.title')}</h2>
        <GlassCard>
          <form
            className="spawn-form"
            onSubmit={(e) => {
              e.preventDefault();
              submit();
            }}
          >
            <div className="field-group">
              <label className="field-label" htmlFor="spawn-name">
                {t('team:spawn.field.name')}
              </label>
              <input
                id="spawn-name"
                className="field input"
                value={name}
                placeholder="repo_scout"
                onChange={(e) => setName(e.target.value)}
              />
              <span className="field-help">{t('team:spawn.field.nameHelp')}</span>
            </div>
            <div className="field-group">
              <label className="field-label" htmlFor="spawn-desc">
                {t('team:spawn.field.description')}
              </label>
              <input
                id="spawn-desc"
                className="field input"
                value={description}
                placeholder={t('team:spawn.field.descriptionPlaceholder')}
                onChange={(e) => setDescription(e.target.value)}
              />
            </div>
            <div className="spawn-form__row">
              <div className="field-group">
                <span className="field-label">{t('team:spawn.field.mode')}</span>
                <GlassSelect
                  aria-label={t('team:spawn.field.mode')}
                  value={mode}
                  options={MODE_OPTIONS.map((o) => ({ value: o.value, label: t(o.labelKey) }))}
                  onChange={setMode}
                />
              </div>
              <div className="field-group">
                <span className="field-label">{t('team:spawn.field.persona')}</span>
                <GlassSelect
                  aria-label={t('team:spawn.field.persona')}
                  value={persona}
                  options={[
                    { value: '', label: t('team:persona.unbound') },
                    ...personas.map((p) => ({ value: p.key, label: p.display_name })),
                  ]}
                  onChange={setPersona}
                />
              </div>
            </div>
            <div className="spawn-form__row">
              <div className="field-group">
                <label className="field-label" htmlFor="spawn-rounds">
                  {t('team:spawn.field.maxRounds')}
                </label>
                <input
                  id="spawn-rounds"
                  className="field input"
                  type="number"
                  min={1}
                  placeholder={t('team:option.followGlobal')}
                  value={maxRounds}
                  onChange={(e) => setMaxRounds(e.target.value)}
                />
                <span className="field-help">{t('team:spawn.field.maxRoundsHelp')}</span>
              </div>
              <div className="field-group">
                <label className="field-label" htmlFor="spawn-tool-rounds">
                  {t('team:spawn.field.maxToolRounds')}
                </label>
                <input
                  id="spawn-tool-rounds"
                  className="field input"
                  type="number"
                  min={1}
                  placeholder={t('team:option.followGlobal')}
                  value={maxToolRounds}
                  onChange={(e) => setMaxToolRounds(e.target.value)}
                />
              </div>
            </div>
            <div className="field-group">
              <span className="field-label">{t('team:spawn.field.network')}</span>
              <GlassSelect
                aria-label={t('team:spawn.field.networkAria')}
                value={networkMode}
                options={NETWORK_OPTIONS.map((o) => ({ value: o.value, label: t(o.labelKey) }))}
                onChange={setNetworkMode}
              />
              <span className="field-help">{t('team:spawn.field.networkHelp')}</span>
            </div>
            <SpawnToolFields
              toolMode={toolMode}
              onToolMode={setToolMode}
              tools={tools}
              pickedTools={pickedTools}
              onToggleTool={toggleTool}
            />
            {formError && <p className="field-error">{formError}</p>}
            <div>
              <button type="button" className="btn btn-primary" disabled={busy} onClick={submit}>
                {t('team:spawn.action.register')}
              </button>
            </div>
          </form>
        </GlassCard>
      </section>

      <ConfirmDialog
        open={confirmOverwrite}
        title={t('team:spawn.confirm.overwriteTitle')}
        message={t('team:spawn.confirm.overwriteMessage', { name: name.trim() })}
        confirmLabel={t('team:spawn.confirm.overwrite')}
        danger
        onConfirm={() => {
          setConfirmOverwrite(false);
          void doRegister();
        }}
        onCancel={() => setConfirmOverwrite(false)}
      />
    </>
  );
}
