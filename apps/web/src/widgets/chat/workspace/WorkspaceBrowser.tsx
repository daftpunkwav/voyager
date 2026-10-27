/**
 * @file WorkspaceBrowser
 * @description Machine-wide directory chooser of the composer workspace
 * switch: type a path or navigate from drives/home. Rendered inside the
 * shared ModalOverlay (already portaled to body): ancestors like the composer
 * carry backdrop-filter, which would clip a locally fixed dialog.
 *
 * Responsibilities:
 * - Render the path input, the quick navigation chips and the directory list
 * - Report the chosen directory to the caller and the dismissal to the caller
 *
 * Constraints:
 * - The chooser never performs the workspace switch itself; the chip chrome
 *   confirms and performs it.
 * - Navigation always goes through a listing of the picker API.
 */

import { useTranslation } from 'react-i18next';
import { WorkspaceDirectoryList } from '@/widgets/chat/workspace/WorkspaceDirectoryList';
import { useWorkspaceDirectory } from '@/widgets/chat/workspace/useWorkspaceDirectory';

export interface WorkspaceBrowserProps {
  /** Report the directory the user chose. */
  onPick: (path: string) => void;
  /** Dismiss the chooser without choosing a directory. */
  onClose: () => void;
}

/** Machine-wide directory chooser. */
export function WorkspaceBrowser({ onPick, onClose }: WorkspaceBrowserProps) {
  const { t } = useTranslation('chat');
  const { pathInput, setPathInput, current, failureMessage, load, enter } = useWorkspaceDirectory();

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
              onClick={() => {
                if (current?.parent) enter(current.parent);
              }}
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

      <WorkspaceDirectoryList current={current} onEnter={enter} />

      {failureMessage ? (
        <p className="ws-browser__error" role="alert">
          {failureMessage}
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
