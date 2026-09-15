/**
 * @file WorkspacePanel
 * @description Chat side panel workspace section: shows the configured agent
 * workspace, a lazy-loading file tree (directories expand, files preview a
 * capped text view), and a machine-wide directory chooser (drives/home/
 * crumbs navigation) for picking a new workspace root. Picking hot-switches
 * the agent (rebuild, no service restart) through POST /api/workspace/switch,
 * which persists agent.workspace.dir itself.
 */

import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { callCapability } from '@/bridge/client';
import { useChatStore } from '@/stores/chatStore';
import { WORKDIR_KEY } from '@/components/settings/agent/constants';
import {
  type PickResult,
  type WorkspaceEntry,
  listWorkspace,
  pickDirectory,
  readWorkspaceFile,
  switchWorkspace,
} from '@/api/workspace';

function joinPath(base: string, name: string): string {
  return base ? `${base}/${name}` : name;
}

/** Machine-wide directory chooser: type a path or navigate from drives/home. */
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

  return (
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
    </div>
  );
}

export function WorkspaceSection() {
  const { t } = useTranslation('chat');
  const workspaceRev = useChatStore((s) => s.workspaceRev);
  const [value, setValue] = useState('');
  const [loaded, setLoaded] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState('');
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [browserOpen, setBrowserOpen] = useState(false);
  const [tree, setTree] = useState<Record<string, WorkspaceEntry[]>>({});
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});
  const [preview, setPreview] = useState<{
    path: string;
    lines: string[];
    truncated: boolean;
  } | null>(null);

  useEffect(() => {
    let alive = true;
    callCapability<{ value?: unknown }>('settings', 'get_setting', { key: WORKDIR_KEY })
      .then((item) => {
        if (!alive) return;
        setValue(typeof item?.value === 'string' ? item.value : '');
        setLoaded(true);
      })
      .catch(() => {
        if (alive) setLoaded(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  // Root level of the file tree: load once the configured path is known.
  useEffect(() => {
    if (!loaded) return;
    let alive = true;
    listWorkspace('')
      .then((res) => {
        if (!alive) return;
        if (res.error) {
          setError(res.error.message);
          return;
        }
        setTree((prev) => ({ ...prev, '': res.entries }));
      })
      .catch((err) => {
        if (alive) setError(err instanceof Error ? err.message : t('chat:workspace.loadFailed'));
      });
    return () => {
      alive = false;
    };
  }, [loaded, t]);

  // Cross-tab switch: another tab rebuilt the agent around a new root.
  // Re-read the configured value and reset the tree/preview (expanded state
  // is dropped: old paths may not exist under the new root).
  const revRef = useRef(workspaceRev);
  useEffect(() => {
    if (revRef.current === workspaceRev) return;
    revRef.current = workspaceRev;
    let alive = true;
    callCapability<{ value?: unknown }>('settings', 'get_setting', { key: WORKDIR_KEY })
      .then((item) => {
        if (!alive) return;
        if (typeof item?.value === 'string') setValue(item.value);
        setTree({});
        setExpanded({});
        setPreview(null);
        return listWorkspace('');
      })
      .then((res) => {
        if (!alive || !res) return;
        if (!res.error) setTree({ '': res.entries });
        else setError(res.error.message);
      })
      .catch((err) => {
        if (alive) setError(err instanceof Error ? err.message : t('chat:workspace.loadFailed'));
      });
    return () => {
      alive = false;
    };
  }, [workspaceRev, t]);

  const persist = async (next: string) => {
    setSaving(true);
    setError(null);
    try {
      // Hot-switch rebuilds the agent (in-flight turns are drained); confirm
      // first since the switch interrupts running work.
      if (!window.confirm(t('chat:workspace.switchConfirm'))) return;
      const res = await switchWorkspace(next);
      setValue(res.workspace);
      setEditing(false);
      setSaved(true);
      setTree({});
      setExpanded({});
      setPreview(null);
      const tree = await listWorkspace('');
      if (!tree.error) setTree({ '': tree.entries });
      else setError(tree.error.message);
    } catch (err) {
      setError(err instanceof Error ? err.message : t('chat:workspace.switchFailed'));
    } finally {
      setSaving(false);
    }
  };

  const save = async () => {
    const next = draft.trim();
    if (!next || next === value) {
      setEditing(false);
      return;
    }
    await persist(next);
  };

  const toggleDir = async (path: string) => {
    const isOpen = expanded[path];
    setExpanded((prev) => ({ ...prev, [path]: !isOpen }));
    if (!isOpen && !tree[path]) {
      try {
        const res = await listWorkspace(path);
        if (res.error) {
          setError(res.error.message);
          return;
        }
        setTree((prev) => ({ ...prev, [path]: res.entries }));
      } catch (err) {
        setError(err instanceof Error ? err.message : t('chat:workspace.loadFailed'));
      }
    }
  };

  const openPreview = async (path: string) => {
    try {
      const res = await readWorkspaceFile(path);
      if (res.error) {
        setError(res.error.message);
        return;
      }
      setPreview({ path, lines: res.lines, truncated: res.truncated });
    } catch (err) {
      setError(err instanceof Error ? err.message : t('chat:workspace.previewFailed'));
    }
  };

  const rootEntries = tree[''];

  return (
    <section className="chat-side__section">
      <div className="chat-side__head chat-side__head--static">
        <span className="chat-side__title">{t('chat:workspace.title')}</span>
        <button
          type="button"
          className="chat-side__meta chat-ws__browsebtn"
          onClick={() => setBrowserOpen(true)}
        >
          {t('chat:workspace.browse')}
        </button>
      </div>
      <div className="chat-side__body">
        {editing ? (
          <div className="chat-ws__edit">
            <input
              className="field input"
              value={draft}
              placeholder={t('chat:workspace.pathPlaceholder')}
              aria-label={t('chat:workspace.title')}
              autoFocus
              onChange={(e) => {
                setDraft(e.target.value);
                setSaved(false);
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter') void save();
                if (e.key === 'Escape') setEditing(false);
              }}
            />
            <div className="chat-ws__actions">
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => setEditing(false)}
              >
                {t('chat:workspace.cancel')}
              </button>
              <button
                type="button"
                className="btn btn-primary btn-sm"
                disabled={saving || !draft.trim()}
                onClick={() => void save()}
              >
                {t('chat:workspace.save')}
              </button>
            </div>
          </div>
        ) : (
          <button
            type="button"
            className="chat-ws__path"
            title={t('chat:workspace.edit')}
            onClick={() => {
              setDraft(value);
              setEditing(true);
            }}
          >
            <span className="chat-ws__value">{loaded ? value || 'data/workspace' : '…'}</span>
            <span className="chat-ws__editbtn">{t('chat:workspace.edit')}</span>
          </button>
        )}

        {loaded ? (
          <ul className="chat-ws__tree small">
            {(rootEntries ?? []).map((e) => (
              <li key={e.name}>
                {e.type === 'directory' ? (
                  <button
                    type="button"
                    className="chat-ws__row"
                    onClick={() => void toggleDir(e.name)}
                  >
                    <span className="chat-ws__mark">{expanded[e.name] ? '▾' : '▸'}</span>
                    {e.name}
                  </button>
                ) : (
                  <button
                    type="button"
                    className="chat-ws__row"
                    onClick={() => void openPreview(e.name)}
                  >
                    <span className="chat-ws__mark">·</span>
                    {e.name}
                  </button>
                )}
                {e.type === 'directory' && expanded[e.name] && tree[e.name] ? (
                  <ul className="chat-ws__tree">
                    {tree[e.name].map((c) => (
                      <li key={c.name}>
                        {c.type === 'file' ? (
                          <button
                            type="button"
                            className="chat-ws__row"
                            onClick={() => void openPreview(joinPath(e.name, c.name))}
                          >
                            <span className="chat-ws__mark">·</span>
                            {c.name}
                          </button>
                        ) : (
                          <span className="chat-ws__row is-static">
                            <span className="chat-ws__mark">▸</span>
                            {c.name}
                          </span>
                        )}
                      </li>
                    ))}
                    {tree[e.name].length === 0 ? (
                      <li className="chat-ws__row is-static muted">
                        {t('chat:workspace.emptyDir')}
                      </li>
                    ) : null}
                  </ul>
                ) : null}
              </li>
            ))}
            {(rootEntries ?? []).length === 0 ? (
              <li className="muted">{t('chat:workspace.emptyTree')}</li>
            ) : null}
          </ul>
        ) : null}

        {preview ? (
          <div className="chat-ws__preview">
            <div className="chat-ws__previewhead">
              <span className="chat-ws__previewpath">{preview.path}</span>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => setPreview(null)}
              >
                ×
              </button>
            </div>
            <pre className="chat-ws__previewtext">
              {preview.lines.join('\n')}
              {preview.truncated ? '\n…' : ''}
            </pre>
          </div>
        ) : null}

        <p className="chat-ws__hint small muted">{t('chat:workspace.hint')}</p>
        {saved ? <p className="chat-ws__saved small">{t('chat:workspace.saved')}</p> : null}
        {error ? (
          <p className="chat-ws__error small" role="alert">
            {error}
          </p>
        ) : null}
      </div>
      {browserOpen ? (
        <WorkspaceBrowser
          onPick={(path) => {
            setDraft(path);
            setEditing(true);
            setBrowserOpen(false);
            setSaved(false);
          }}
          onClose={() => setBrowserOpen(false)}
        />
      ) : null}
    </section>
  );
}
