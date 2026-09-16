/**
 * @file WorkspaceChip
 * @description Composer-bar workspace button: shows the current directory's
 * name; clicking opens the machine-wide directory chooser (drives/home
 * navigation) and hot-switches the agent (rebuild, no service restart)
 * through POST /api/workspace/switch, which persists agent.workspace.dir
 * itself. The chosen surface renders through a portal so fixed positioning
 * stays viewport-relative inside the filtered composer.
 */

import { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import { callCapability } from '@/bridge/client';
import { useChatStore } from '@/stores/chatStore';
import { useUIStore } from '@/stores/uiStore';
import { WORKDIR_KEY } from '@/components/settings/agent/constants';
import { type PickResult, pickDirectory, switchWorkspace } from '@/api/workspace';

/**
 * Shared workspace hot-switch flow: confirm first (the switch rebuilds the
 * agent and drains in-flight turns), then POST the switch. A request id is
 * stashed in chatStore before the POST: the broadcast reaches this tab too,
 * and the marker lets useChatStream tell this tab's own switch apart from
 * another tab's. Resolves to the new workspace path, or null when the user
 * dismissed the confirm; errors propagate to the caller for surface-specific
 * display.
 */
function useWorkspaceSwitch() {
  const { t } = useTranslation('chat');
  const [switching, setSwitching] = useState(false);
  const applySwitch = async (next: string): Promise<string | null> => {
    if (!window.confirm(t('chat:workspace.switchConfirm'))) return null;
    // Stash before the POST: the SSE echo races the HTTP response, so the
    // marker must already be in place when the event lands. A leftover
    // marker (request failed / event lost) is inert: only an exact match
    // suppresses, and the next switch overwrites it.
    const marker = crypto.randomUUID();
    useChatStore.setState({ workspaceSwitchMarker: marker });
    setSwitching(true);
    try {
      const res = await switchWorkspace(next, marker);
      return res.workspace;
    } finally {
      setSwitching(false);
    }
  };
  return { applySwitch, switching };
}

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
  const { applySwitch, switching } = useWorkspaceSwitch();

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
    try {
      const ws = await applySwitch(path);
      if (ws) setValue(ws);
    } catch (err) {
      useUIStore.getState().addToast({
        type: 'error',
        message: err instanceof Error ? err.message : t('chat:workspace.switchFailed'),
      });
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
      {browserOpen ? (
        <WorkspaceBrowser
          onPick={(path) => void pick(path)}
          onClose={() => setBrowserOpen(false)}
        />
      ) : null}
    </>
  );
}

/** Machine-wide directory chooser: type a path or navigate from drives/home.
 *  Rendered through a portal: ancestors like the composer carry
 *  backdrop-filter, which turns fixed positioning into their local
 *  coordinate space and would clip the dialog. */
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

  return createPortal(
    <div
      className="ask-mask"
      role="dialog"
      aria-modal="true"
      aria-label={t('chat:workspace.browserTitle')}
    >
      <div className="llm-model-dialog glass-card glass-card--dialog">
        <h3 className="llm-model-dialog__title">{t('chat:workspace.browserTitle')}</h3>
        <div className="chat-ws__browserbar">
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
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            onClick={() => void load(pathInput)}
          >
            {t('chat:workspace.go')}
          </button>
        </div>
        <div className="chat-ws__browserbar">
          {current?.parent ? (
            <button
              type="button"
              className="composer-dd__item chat-ws__up"
              onClick={() => {
                const parent = current.parent as string;
                setPathInput(parent);
                void load(parent);
              }}
            >
              ↑ {t('chat:workspace.up')}
            </button>
          ) : null}
          {current?.home ? (
            <button
              type="button"
              className="composer-dd__item chat-ws__up"
              onClick={() => {
                setPathInput(current.home);
                void load(current.home);
              }}
            >
              {t('chat:workspace.home')}
            </button>
          ) : null}
        </div>
        <ul className="chat-ws__listing">
          {entries.map((e) => (
            <li key={e.name}>
              <button
                type="button"
                className="composer-dd__item"
                onClick={() => {
                  const next = current?.path
                    ? `${current.path.replace(/[\\/]+$/, '')}/${e.name}`
                    : e.name;
                  setPathInput(next);
                  void load(next);
                }}
              >
                {e.name}
              </button>
            </li>
          ))}
          {entries.length === 0 ? (
            <li className="small muted">{t('chat:workspace.noDirs')}</li>
          ) : null}
        </ul>
        {error ? (
          <p className="chat-ws__error small" role="alert">
            {error}
          </p>
        ) : null}
        <div className="llm-model-dialog__actions">
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
    </div>,
    document.body
  );
}
