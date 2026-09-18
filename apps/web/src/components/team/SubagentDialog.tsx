/**
 * @file SubagentDialog
 * @description Create/edit dialog for custom subagent definitions, rendered in
 * a ModalOverlay (the reference "新建子智能体" window). Create and edit share
 * one form: edit mode locks the name, exposes delete, and re-registers the
 * same definition name on save.
 *
 * Data (personas / tools / existing names) comes in via props from the
 * section; saving goes through register_subagent and reports back via onSaved.
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { deleteSubagent, registerSubagent } from '@/api/agent';
import { useUIStore } from '@/stores/uiStore';
import { ModalOverlay } from '@/components/common/ModalOverlay';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { GlassSelect } from '@/components/common/GlassSelect';
import { Switch } from '@/components/common/Switch';
import { extractErrorMessage } from '@/utils/errors';
import { NAME_RE, MODE_OPTIONS, NETWORK_OPTIONS } from './constants';
import { ToolPicker } from './ToolPicker';
import type { PersonaItem, SubagentDef, ToolItem } from './types';

interface SubagentDialogProps {
  open: boolean;
  /** Null = create mode; otherwise the definition being edited. */
  editing: SubagentDef | null;
  personas: PersonaItem[];
  tools: ToolItem[];
  /** All registered names (duplicate check on create). */
  existingNames: string[];
  onClose: () => void;
  onSaved: () => void;
}

interface FormState {
  name: string;
  description: string;
  mode: string;
  persona: string;
  toolMode: 'all' | 'custom';
  pickedTools: string[];
  maxRounds: string;
  maxToolCalls: string;
  networkMode: string;
  readonly: boolean;
  enabled: boolean;
}

function formFromDef(def: SubagentDef | null): FormState {
  return {
    name: def?.name ?? '',
    description: def?.description ?? '',
    mode: def?.mode ?? 'react',
    persona: def?.persona ?? '',
    toolMode: def?.allowed_tools == null ? 'all' : 'custom',
    pickedTools: def?.allowed_tools ?? [],
    maxRounds: def?.max_rounds != null ? String(def.max_rounds) : '',
    maxToolCalls: def?.max_tool_calls != null ? String(def.max_tool_calls) : '',
    networkMode: def?.network_mode ?? '',
    readonly: def?.readonly ?? false,
    enabled: def?.enabled ?? true,
  };
}

function parseRounds(draft: string): number | null {
  const trimmed = draft.trim();
  if (trimmed === '') return null;
  const n = Number(trimmed);
  if (!Number.isInteger(n) || n < 1) return NaN;
  return n;
}

export function SubagentDialog({
  open,
  editing,
  personas,
  tools,
  existingNames,
  onClose,
  onSaved,
}: SubagentDialogProps) {
  const { t } = useTranslation('team');
  const addToast = useUIStore((s) => s.addToast);
  const [form, setForm] = useState<FormState>(() => formFromDef(editing));
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState('');
  const [confirmOverwrite, setConfirmOverwrite] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);

  // Re-seed the form whenever the dialog opens for another target; while open,
  // editing stays pinned by the parent, so this only fires on open/edit switch.
  useEffect(() => {
    if (open) {
      setForm(formFromDef(editing));
      setFormError('');
    }
  }, [open, editing]);

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((prev) => ({ ...prev, [key]: value }));

  const toggleTool = (name: string) =>
    setForm((prev) => ({
      ...prev,
      pickedTools: prev.pickedTools.includes(name)
        ? prev.pickedTools.filter((n) => n !== name)
        : [...prev.pickedTools, name],
    }));

  const toggleGroup = (names: string[], picked: boolean) =>
    setForm((prev) => ({
      ...prev,
      pickedTools: picked
        ? [...new Set([...prev.pickedTools, ...names])]
        : prev.pickedTools.filter((n) => !names.includes(n)),
    }));

  const doSave = async () => {
    setBusy(true);
    setFormError('');
    try {
      const args: Record<string, unknown> = {
        name: form.name.trim(),
        description: form.description.trim(),
        mode: form.mode,
        persona: form.persona,
        readonly: form.readonly,
        enabled: form.enabled,
      };
      if (form.toolMode === 'custom') args.allowed_tools = form.pickedTools;
      if (form.maxRounds.trim() !== '') args.max_rounds = Number(form.maxRounds);
      if (form.maxToolCalls.trim() !== '') args.max_tool_calls = Number(form.maxToolCalls);
      if (form.networkMode) args.network_mode = form.networkMode;
      await registerSubagent(args);
      addToast({
        type: 'success',
        message: editing
          ? t('team:mgr.updated', { name: form.name.trim() })
          : t('team:spawn.toast.registered', { name: form.name.trim() }),
      });
      onSaved();
      onClose();
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
    const trimmedName = form.name.trim();
    if (!NAME_RE.test(trimmedName)) {
      setFormError(t('team:spawn.error.name'));
      return;
    }
    if (!form.description.trim()) {
      setFormError(t('team:spawn.error.description'));
      return;
    }
    if (form.toolMode === 'custom' && form.pickedTools.length === 0) {
      setFormError(t('team:spawn.error.tools'));
      return;
    }
    if (Number.isNaN(parseRounds(form.maxRounds))) {
      setFormError(t('team:spawn.error.maxRounds'));
      return;
    }
    if (Number.isNaN(parseRounds(form.maxToolCalls))) {
      setFormError(t('team:spawn.error.maxToolRounds'));
      return;
    }
    setFormError('');
    // Create mode only: overwriting an unrelated existing definition needs an
    // explicit confirm; edit mode already targets that exact definition.
    if (!editing && existingNames.includes(trimmedName)) {
      setConfirmOverwrite(true);
      return;
    }
    void doSave();
  };

  const doDelete = async () => {
    if (!editing) return;
    setBusy(true);
    try {
      await deleteSubagent(editing.name);
      addToast({ type: 'success', message: t('team:mgr.deleted', { name: editing.name }) });
      setConfirmDelete(false);
      onSaved();
      onClose();
    } catch (err) {
      addToast({
        type: 'error',
        message: t('team:mgr.deleteFailed', { message: extractErrorMessage(err) }),
      });
    } finally {
      setBusy(false);
      setConfirmDelete(false);
    }
  };

  return (
    <>
      <ModalOverlay open={open} onClose={onClose}>
        <div
          className="modal glass-card glass-card--dialog subagent-dialog"
          role="dialog"
          aria-modal="true"
          aria-label={
            editing ? t('team:mgr.editTitle', { name: editing.name }) : t('team:mgr.createTitle')
          }
          onClick={(e) => e.stopPropagation()}
        >
          <h3 className="subagent-dialog__title">
            {editing ? t('team:mgr.editTitle', { name: editing.name }) : t('team:mgr.createTitle')}
          </h3>

          <div className="subagent-dialog__grid">
            <div className="field-group">
              <label className="field-label" htmlFor="subagent-name">
                {t('team:spawn.field.name')}
              </label>
              <input
                id="subagent-name"
                className="field input"
                value={form.name}
                placeholder="repo_scout"
                disabled={editing !== null}
                onChange={(e) => set('name', e.target.value)}
              />
              <span className="field-help">{t('team:spawn.field.nameHelp')}</span>
            </div>
            <div className="field-group">
              <span className="field-label">{t('team:spawn.field.mode')}</span>
              <GlassSelect
                aria-label={t('team:spawn.field.mode')}
                value={form.mode}
                options={MODE_OPTIONS.map((o) => ({ value: o.value, label: t(o.labelKey) }))}
                onChange={(v) => set('mode', v)}
              />
            </div>
          </div>

          <div className="field-group">
            <label className="field-label" htmlFor="subagent-desc">
              {t('team:spawn.field.description')}
            </label>
            <input
              id="subagent-desc"
              className="field input"
              value={form.description}
              placeholder={t('team:spawn.field.descriptionPlaceholder')}
              onChange={(e) => set('description', e.target.value)}
            />
          </div>

          <div className="subagent-dialog__grid">
            <div className="field-group">
              <span className="field-label">{t('team:spawn.field.persona')}</span>
              <GlassSelect
                aria-label={t('team:spawn.field.persona')}
                value={form.persona}
                options={[
                  { value: '', label: t('team:persona.unbound') },
                  ...personas.map((p) => ({ value: p.key, label: p.display_name })),
                ]}
                onChange={(v) => set('persona', v)}
              />
            </div>
            <div className="field-group">
              <span className="field-label">{t('team:spawn.field.network')}</span>
              <GlassSelect
                aria-label={t('team:spawn.field.networkAria')}
                value={form.networkMode}
                options={NETWORK_OPTIONS.map((o) => ({ value: o.value, label: t(o.labelKey) }))}
                onChange={(v) => set('networkMode', v)}
              />
              <span className="field-help">{t('team:spawn.field.networkHelp')}</span>
            </div>
          </div>

          <div className="subagent-dialog__grid">
            <div className="field-group">
              <label className="field-label" htmlFor="subagent-rounds">
                {t('team:spawn.field.maxRounds')}
              </label>
              <input
                id="subagent-rounds"
                className="field input"
                type="number"
                min={1}
                placeholder={t('team:option.followGlobal')}
                value={form.maxRounds}
                onChange={(e) => set('maxRounds', e.target.value)}
              />
            </div>
            <div className="field-group">
              <label className="field-label" htmlFor="subagent-tool-calls">
                {t('team:spawn.field.maxToolRounds')}
              </label>
              <input
                id="subagent-tool-calls"
                className="field input"
                type="number"
                min={1}
                placeholder={t('team:option.followGlobal')}
                value={form.maxToolCalls}
                onChange={(e) => set('maxToolCalls', e.target.value)}
              />
            </div>
          </div>

          <div className="field-group">
            <span className="field-label">{t('team:spawnTools.label')}</span>
            <div className="subagent-dialog__toolmode">
              <label className="subagent-dialog__toolmode-option">
                <input
                  type="radio"
                  name="subagent-tool-mode"
                  checked={form.toolMode === 'all'}
                  onChange={() => set('toolMode', 'all')}
                />
                {t('team:tools.unrestricted')}
              </label>
              <label className="subagent-dialog__toolmode-option">
                <input
                  type="radio"
                  name="subagent-tool-mode"
                  checked={form.toolMode === 'custom'}
                  onChange={() => set('toolMode', 'custom')}
                />
                {t('team:spawnTools.custom')}
              </label>
            </div>
            {form.toolMode === 'custom' && (
              <ToolPicker
                tools={tools}
                pickedTools={form.pickedTools}
                onToggleTool={toggleTool}
                onToggleGroup={toggleGroup}
              />
            )}
            <span className="field-help">{t('team:spawnTools.help')}</span>
          </div>

          <div className="subagent-dialog__toggles">
            <div className="subagent-dialog__toggle">
              <Switch
                checked={form.enabled}
                small
                ariaLabel={t('team:mgr.enabled')}
                onChange={(v) => set('enabled', v)}
              />
              <div>
                <div className="subagent-dialog__toggle-label">{t('team:mgr.enabled')}</div>
                <div className="subagent-dialog__toggle-help">{t('team:mgr.enabledHelp')}</div>
              </div>
            </div>
            <div className="subagent-dialog__toggle">
              <Switch
                checked={form.readonly}
                small
                ariaLabel={t('team:mgr.readonly')}
                onChange={(v) => set('readonly', v)}
              />
              <div>
                <div className="subagent-dialog__toggle-label">{t('team:mgr.readonly')}</div>
                <div className="subagent-dialog__toggle-help">{t('team:mgr.readonlyHelp')}</div>
              </div>
            </div>
          </div>

          {formError && <p className="field-error">{formError}</p>}

          <div className="subagent-dialog__footer">
            {editing && (
              <button
                type="button"
                className="btn btn-danger"
                disabled={busy}
                onClick={() => setConfirmDelete(true)}
              >
                {t('settings:common.delete')}
              </button>
            )}
            <div className="subagent-dialog__footer-main">
              <button type="button" className="btn btn-ghost" disabled={busy} onClick={onClose}>
                {t('settings:common.cancel')}
              </button>
              <button type="button" className="btn btn-primary" disabled={busy} onClick={submit}>
                {t('team:mgr.save')}
              </button>
            </div>
          </div>
        </div>
      </ModalOverlay>

      <ConfirmDialog
        open={confirmOverwrite}
        title={t('team:spawn.confirm.overwriteTitle')}
        message={t('team:spawn.confirm.overwriteMessage', { name: form.name.trim() })}
        confirmLabel={t('team:spawn.confirm.overwrite')}
        danger
        onConfirm={() => {
          setConfirmOverwrite(false);
          void doSave();
        }}
        onCancel={() => setConfirmOverwrite(false)}
      />

      <ConfirmDialog
        open={confirmDelete}
        title={t('team:mgr.deleteTitle')}
        message={t('team:mgr.deleteConfirm', { name: editing?.name ?? '' })}
        confirmLabel={t('settings:common.delete')}
        danger
        onConfirm={() => void doDelete()}
        onCancel={() => setConfirmDelete(false)}
      />
    </>
  );
}
