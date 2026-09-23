/**
 * @file WorkspaceChip
 * @description Composer-bar workspace button: shows the current directory's
 * name; clicking opens the machine-wide directory chooser (drives/home
 * navigation) and hot-switches the agent (rebuild, no service restart)
 * through the shared workspaceSwitch bridge, which persists
 * agent.workspace.dir itself. The chooser renders through the shared
 * ModalOverlay (portaled to body) so composer backdrop-filter cannot clip it.
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { callCapability } from '@/bridge/client';
import { switchWorkspaceWithMarker } from '@/bridge/workspaceSwitch';
import { ModalOverlay } from '@/components/common/ModalOverlay';
import { useChatStore } from '@/stores/chatStore';
import { confirmDialog, useUIStore } from '@/stores/uiStore';
import { type PickResult, pickDirectory, WORKDIR_KEY } from '@/api/workspace';

/**
 * Workspace path button for the composer bar (bottom-left of the input):
 * shows the current directory's name only (full path in the tooltip); the
 * click opens the directory chooser to switch the workspace. Re-reads on
 * workspaceRev so cross-tab hot-switches stay fresh.
 */
export function WorkspacePathChip() {
  const { t } = useTranslation('chat');
  const workspaceRev = useChatStore((s) => s.workspaceRev);
  const [value, setValue] = useState('');
  const [browserOpen, setBrowserOpen] = useState(false);
  const [switching, setSwitching] = useState(false);

  useEffect(() => {
    let alive = true;
    callCapability<{ value?: unknown }>('settings', 'get_setting', { key: WORKDIR_KEY })
      .then((item) => {
        if (alive && typeof item?.value === 'string') setValue(item.value);
      })
      .catch(() => {}); // indicator hidden until a value arrives
    return () => {
      alive = false;
    };
  }, [workspaceRev]);

  if (!value) return null;
  // Current directory name only — parents stay out of the bar.
  const leaf = value.split(/[\\/]/).filter(Boolean).pop() ?? value;

  const pick = async (path: string) => {
    setBrowserOpen(false);
    const ok = await confirmDialog({ message: t('chat:workspace.switchConfirm') });
    if (!ok) return;
    setSwitching(true);
    try {
      const ws = await switchWorkspaceWithMarker(path);
      if (ws) setValue(ws);
    } catch (err) {
      useUIStore.getState().addToast({
        type: 'error',
        message: err instanceof Error ? err.message : t('chat:workspace.switchFailed'),
      });
    } finally {
      setSwitching(false);
    }
  };

  return (
    <>
      <button
        type="button"
        className="composer-ws"
        title={value}
        aria-label={`${t('chat:workspace.title')}: ${value}`}
        disabled={switching}
        onClick={() => setBrowserOpen(true)}
      >
        {leaf}
      </button>
      <ModalOverlay open={browserOpen} onClose={() => setBrowserOpen(false)}>
        <WorkspaceBrowser
          onPick={(path) => void pick(path)}
          onClose={() => setBrowserOpen(false)}
        />
      </ModalOverlay>
    </>
  );
}

/**
 * Machine-wide directory chooser: type a path or navigate from drives/home.
 * Rendered inside the shared ModalOverlay (already portaled to body):
 * ancestors like the composer carry backdrop-filter, which would clip a
 * locally fixed dialog.
 */
function WorkspaceBrowser({
  onPick,
  onClose,
}: {
  onPick: (path: string) => void;
  onClose: () => void;
}) {
  const { t } = useTranslation('chat');
  const [pathInput, setPathInput] = useState('');
  const [current, setCurrent] = useState<PickResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = async (path: string) => {
    setError(null);
    try {
      const res = await pickDirectory(path);
      if (res.error) {
        setError(res.error.message);
        return;
      }
      setCurrent(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('chat:workspace.loadFailed'));
    }
  };

  useEffect(() => {
    void load('');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const entries = (current?.entries ?? []).filter((e) => e.type === 'directory');

  const enter = (next: string) => {
    setPathInput(next);
    void load(next);
  };

  return (
    <div
      className="ws-browser glass-card glass-card--dialog"
      role="dialog"
      aria-modal="true"
      aria-label={t('chat:workspace.browserTitle')}
      onClick={(e) => e.stopPropagation()}
    >
      <h3 className="modal__title">{t('chat:workspace.browserTitle')}</h3>

      <div className="ws-browser__pathrow">
        <input
          className="field input"
          value={pathInput}
          placeholder={t('chat:workspace.pathPlaceholder')}
          aria-label={t('chat:workspace.pathPlaceholder')}
          onChange={(e) => setPathInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') void load(pathInput);
          }}
        />
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => void load(pathInput)}>
          {t('chat:workspace.go')}
        </button>
      </div>

      {current?.parent || current?.home ? (
        <div className="ws-browser__quick">
          {current?.parent ? (
            <button
              type="button"
              className="ws-browser__chip"
              onClick={() => enter(current.parent as string)}
            >
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.2"
                aria-hidden
              >
                <path d="M12 19V5M5 12l7-7 7 7" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              {t('chat:workspace.up')}
            </button>
          ) : null}
          {current?.home ? (
            <button type="button" className="ws-browser__chip" onClick={() => enter(current.home)}>
              <svg
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.2"
                aria-hidden
              >
                <path d="M3 10.5L12 3l9 7.5" strokeLinecap="round" strokeLinejoin="round" />
                <path d="M5 9.5V21h14V9.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              {t('chat:workspace.home')}
            </button>
          ) : null}
        </div>
      ) : null}

      <div
        className="ws-browser__list"
        role="listbox"
        aria-label={t('chat:workspace.browserTitle')}
      >
        {entries.map((e) => (
          <button
            key={e.name}
            type="button"
            role="option"
            aria-selected={false}
            className="ws-browser__row"
            onClick={() => {
              const next = current?.path
                ? `${current.path.replace(/[\\/]+$/, '')}/${e.name}`
                : e.name;
              enter(next);
            }}
          >
            <svg
              className="ws-browser__row-icon"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.9"
              aria-hidden
            >
              <path
                d="M3 7a2 2 0 012-2h4l2 2h8a2 2 0 012 2v9a2 2 0 01-2 2H5a2 2 0 01-2-2V7z"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
            </svg>
            <span className="ws-browser__row-name">{e.name}</span>
          </button>
        ))}
        {entries.length === 0 ? (
          <p className="ws-browser__empty">{t('chat:workspace.noDirs')}</p>
        ) : null}
      </div>

      {error ? (
        <p className="ws-browser__error" role="alert">
          {error}
        </p>
      ) : null}

      <div className="modal__actions">
        <button type="button" className="btn btn-ghost" onClick={onClose}>
          {t('chat:workspace.cancel')}
        </button>
        <button
          type="button"
          className="btn btn-primary"
          disabled={!pathInput.trim()}
          onClick={() => onPick(pathInput.trim())}
        >
          {t('chat:workspace.choose')}
        </button>
      </div>
    </div>
  );
}
