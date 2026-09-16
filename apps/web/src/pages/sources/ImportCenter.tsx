/**
 * @file ImportCenter
 * @description Five-in-one import dialog (GitHub URL / repo search / Stars / document upload / web URL).
 *
 * Document upload = uploadFile to disk + add_document into the store (a two-step
 * combined flow); web URLs = save_url fetch-and-store; repos reuse the existing
 * ImportUrlsModal channel.
 *
 * Responsibilities:
 * - Host the tabbed import dialog: document files, web URL, and GitHub
 *   (URL / search / Stars panes)
 * - Run each pane's flow through the sources api with success/failure
 *   toasts and invalidation on completion
 */

import { useEffect, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { uploadDocument, saveUrl, importRepo } from '@/api/sources';
import { useUIStore } from '@/stores/uiStore';
import { ModalOverlay } from '@/components/common/ModalOverlay';

export type ImportTab = 'files' | 'web' | 'github';

const TABS: { key: ImportTab; labelKey: string }[] = [
  { key: 'files', labelKey: 'sources:kind.doc' },
  { key: 'web', labelKey: 'sources:import.tab.web' },
  { key: 'github', labelKey: 'sources:import.tab.github' },
];

const ACCEPT = '.pdf,.epub,.docx,.txt,.md,.markdown,.zip,.mobi,.azw3,.html';

interface ImportCenterProps {
  open: boolean;
  initialTab?: ImportTab;
  onClose: () => void;
}

export function ImportCenter({ open, initialTab = 'files', onClose }: ImportCenterProps) {
  const { t } = useTranslation('sources');
  const [tab, setTab] = useState<ImportTab>(initialTab);
  useEffect(() => {
    if (open) setTab(initialTab);
  }, [open, initialTab]);
  return (
    <ModalOverlay open={open} onClose={onClose}>
      {open && (
        <div
          className="modal import-center glass-card glass-card--dialog"
          role="dialog"
          aria-modal="true"
          aria-label={t('sources:import.title')}
          onClick={(e) => e.stopPropagation()}
        >
          <header className="import-center__head">
            <h2>{t('sources:import.title')}</h2>
            <nav className="import-center__tabs" role="tablist">
              {TABS.map((tabItem) => (
                <button
                  key={tabItem.key}
                  type="button"
                  role="tab"
                  aria-selected={tab === tabItem.key}
                  className={`import-center__tab ${tab === tabItem.key ? 'is-active' : ''}`}
                  onClick={() => setTab(tabItem.key)}
                >
                  {t(tabItem.labelKey)}
                </button>
              ))}
            </nav>
            <button
              type="button"
              className="icon-btn"
              aria-label={t('sources:closeAria')}
              onClick={onClose}
            >
              ✕
            </button>
          </header>
          <div className="import-center__body">
            {tab === 'files' && <FilesPane onDone={onClose} />}
            {tab === 'web' && <WebPane onDone={onClose} />}
            {tab === 'github' && <GithubPane onDone={onClose} />}
          </div>
        </div>
      )}
    </ModalOverlay>
  );
}

/** Document upload: click or drag, then upload, then parse into the store; unsupported formats surface the backend error. */
function FilesPane({ onDone }: { onDone: () => void }) {
  const { t } = useTranslation('sources');
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const addToast = useUIStore((s) => s.addToast);

  const upload = async (files: FileList | File[]) => {
    const list = Array.from(files);
    if (list.length === 0) return;
    setBusy(true);
    let ok = 0;
    let fail = 0;
    for (const f of list) {
      try {
        await uploadDocument(f);
        ok += 1;
      } catch (err) {
        fail += 1;
        addToast({
          type: 'error',
          message: t('sources:import.fileFailed', {
            name: f.name,
            message: err instanceof Error ? err.message : t('sources:import.uploadFailed'),
          }),
        });
      }
    }
    setBusy(false);
    if (ok > 0) {
      addToast({
        type: 'success',
        message: t('sources:import.docsDone', {
          ok,
          suffix: fail > 0 ? t('sources:import.failSuffix', { count: fail }) : '',
        }),
      });
      onDone();
    }
  };

  return (
    <div
      className={`import-drop ${dragging ? 'is-drag' : ''}`}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={() => setDragging(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        void upload(e.dataTransfer.files);
      }}
      onClick={() => inputRef.current?.click()}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') inputRef.current?.click();
      }}
    >
      <input
        ref={inputRef}
        type="file"
        multiple
        accept={ACCEPT}
        hidden
        onChange={(e) => {
          if (e.target.files) void upload(e.target.files);
          e.target.value = '';
        }}
      />
      <div className="import-drop__icon" aria-hidden>
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.6"
          width={40}
          height={40}
        >
          <path d="M12 16V4M6 10l6-6 6 6" />
          <path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3" />
        </svg>
      </div>
      <p className="import-drop__title">
        {busy ? t('sources:import.dropBusy') : t('sources:import.dropTitle')}
      </p>
      <p className="import-drop__hint">{t('sources:import.dropHint')}</p>
    </div>
  );
}

/** Web URL clipping: fetches a pasted URL list one by one. */
function WebPane({ onDone }: { onDone: () => void }) {
  const { t } = useTranslation('sources');
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const addToast = useUIStore((s) => s.addToast);

  const save = async () => {
    const urls = text
      .split('\n')
      .map((l) => l.trim())
      .filter(Boolean);
    if (urls.length === 0) return;
    setBusy(true);
    let ok = 0;
    let fail = 0;
    for (const url of urls) {
      try {
        await saveUrl(url);
        ok += 1;
      } catch (err) {
        fail += 1;
        addToast({
          type: 'error',
          message: err instanceof Error ? err.message : t('sources:import.urlFailed', { url }),
        });
      }
    }
    setBusy(false);
    if (ok > 0) {
      addToast({
        type: 'success',
        message: t('sources:import.webDone', {
          ok,
          suffix: fail > 0 ? t('sources:import.failSuffix', { count: fail }) : '',
        }),
      });
      onDone();
    }
  };

  return (
    <div className="import-web">
      <textarea
        className="import-web__input"
        rows={5}
        placeholder={t('sources:import.webPlaceholder')}
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      <p className="import-web__hint">{t('sources:import.webHint')}</p>
      <div className="import-web__actions">
        <button
          type="button"
          className="btn btn-primary"
          disabled={busy || !text.trim()}
          onClick={() => void save()}
        >
          {busy ? t('sources:import.webBusy') : t('sources:import.webSave')}
        </button>
      </div>
    </div>
  );
}

/** GitHub: paste repo URLs (one per line) and import them directly in this panel. */
function GithubPane({ onDone }: { onDone: () => void }) {
  const { t } = useTranslation('sources');
  const qc = useQueryClient();
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const addToast = useUIStore((s) => s.addToast);

  const importRepos = async () => {
    const urls = text
      .split('\n')
      .map((l) => l.trim())
      .filter(Boolean);
    if (urls.length === 0) return;
    setBusy(true);
    let ok = 0;
    let fail = 0;
    for (const url of urls) {
      try {
        await importRepo(url);
        ok += 1;
      } catch (err) {
        fail += 1;
        if (urls.length === 1) {
          addToast({
            type: 'error',
            message: err instanceof Error ? err.message : t('sources:import.failed'),
          });
        }
      }
    }
    setBusy(false);
    void qc.invalidateQueries({ queryKey: ['projects'] });
    void qc.invalidateQueries({ queryKey: ['sourcesStream'] });
    if (ok > 0) {
      addToast({
        type: 'success',
        message: t('sources:import.reposDone', {
          ok,
          suffix: fail > 0 ? t('sources:import.failSuffix', { count: fail }) : '',
        }),
      });
      onDone();
    } else if (urls.length > 1) {
      addToast({ type: 'error', message: t('sources:import.reposFailedBatch') });
    }
  };

  return (
    <div className="import-web">
      <textarea
        className="import-web__input"
        rows={5}
        placeholder={t('sources:import.githubPlaceholder')}
        value={text}
        onChange={(e) => setText(e.target.value)}
      />
      <p className="import-web__hint">{t('sources:import.githubHint')}</p>
      <div className="import-web__actions">
        <button
          type="button"
          className="btn btn-primary"
          disabled={busy || !text.trim()}
          onClick={() => void importRepos()}
        >
          {busy ? t('sources:import.githubBusy') : t('sources:importRepos')}
        </button>
      </div>
    </div>
  );
}
