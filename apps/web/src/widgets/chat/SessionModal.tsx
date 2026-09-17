/**
 * @file SessionModal
 * @description Chat session switcher: a centered modal (shared ModalOverlay
 * shell) listing the chat sessions (title / status / active badge) with
 * create, rename, delete, and a one-line context-usage status for the open
 * session. Rows read as hairline regions on the modal glass — the overlay is
 * the single glass layer, no nested cards.
 *
 * Design constraints (workspace conventions):
 * - Overlay dialog, never squeezing the main chat column
 * - Active marking via background/text tone; no brand-colored bars
 * - Delete is a two-click confirm styled with `.is-danger`
 */

import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  type ChatSessionRow,
  type ContextStatus,
  compactSession,
  createSession,
  deleteSession,
  getContextStatus,
  renameSession,
  setActiveSession,
} from '@/api/agent';
import { loadChatSessions, loadSessionTimeline } from '@/bridge/chatSend';
import { useChatStore } from '@/stores/chatStore';
import { useUIStore } from '@/stores/uiStore';
import { ServiceError } from '@/bridge/client';
import { extractErrorMessage } from '@/utils/errors';
import { ModalOverlay } from '@/components/common/ModalOverlay';

interface SessionModalProps {
  open: boolean;
  onClose: () => void;
}

export function SessionModal({ open, onClose }: SessionModalProps) {
  const { t } = useTranslation('chat');
  const sessions = useChatStore((s) => s.sessions);
  const activeId = useChatStore((s) => s.activeSessionId);
  const [busy, setBusy] = useState(false);
  const [confirmingId, setConfirmingId] = useState('');
  const [renamingId, setRenamingId] = useState('');
  const [renameDraft, setRenameDraft] = useState('');
  const [status, setStatus] = useState<ContextStatus | null>(null);

  const refreshList = useCallback(async () => {
    await loadChatSessions();
  }, []);

  useEffect(() => {
    if (!open) return;
    void refreshList();
    setConfirmingId('');
    setRenamingId('');
  }, [open, refreshList]);

  // Context usage line for the open session. The capability returns an
  // {error} shape for sessions that never had a turn — validate the fields
  // so NaN never renders; silent on failure (no status line is fine).
  useEffect(() => {
    if (!open || !activeId) return;
    let alive = true;
    getContextStatus(activeId)
      .then((s) => {
        const ok =
          s &&
          typeof s.used_tokens === 'number' &&
          Number.isFinite(s.used_tokens) &&
          typeof s.used_pct === 'number';
        if (alive) setStatus(ok ? s : null);
      })
      .catch(() => {
        if (alive) setStatus(null);
      });
    return () => {
      alive = false;
    };
  }, [open, activeId]);

  const fail = (err: unknown) => {
    const message = err instanceof ServiceError ? extractErrorMessage(err) : String(err);
    useUIStore.getState().addToast({ type: 'error', message });
  };

  const handleSwitch = async (row: ChatSessionRow) => {
    if (busy || row.session_id === activeId) return;
    setBusy(true);
    try {
      await setActiveSession(row.session_id);
      const loaded = useChatStore.getState().switchSession(row.session_id);
      if (!loaded) await loadSessionTimeline(row.session_id);
      onClose();
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  };

  const handleCreate = async () => {
    if (busy) return;
    setBusy(true);
    try {
      await createSession('');
      await refreshList();
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  };

  const handleRename = async (sessionId: string) => {
    const title = renameDraft.trim();
    setRenamingId('');
    if (!title) return;
    try {
      await renameSession(sessionId, title);
      await refreshList();
    } catch (err) {
      fail(err);
    }
  };

  const handleDelete = async (sessionId: string) => {
    if (confirmingId !== sessionId) {
      setConfirmingId(sessionId);
      return;
    }
    setConfirmingId('');
    try {
      await deleteSession(sessionId);
      await refreshList();
    } catch (err) {
      fail(err);
    }
  };

  const handleCompact = async () => {
    if (busy || !activeId) return;
    setBusy(true);
    try {
      const report = (await compactSession(activeId)) as { mode?: string };
      useUIStore.getState().addToast({
        type: 'success',
        message: t('chat:session.compactDone', { mode: String(report?.mode ?? '') }),
      });
      const s = await getContextStatus(activeId).catch(() => null);
      setStatus(s);
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  };

  return (
    <ModalOverlay open={open} onClose={onClose}>
      <div
        className="modal glass-card glass-card--dialog session-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="session-modal-title"
      >
        <div className="session-modal__head">
          <span id="session-modal-title" className="session-modal__title">
            {t('chat:session.drawerTitle')}
          </span>
          <div className="session-modal__head-actions">
            <button
              type="button"
              className="btn btn-sm"
              disabled={busy}
              onClick={() => void handleCreate()}
            >
              {t('chat:session.new')}
            </button>
            <button
              type="button"
              className="btn btn-sm"
              onClick={onClose}
              aria-label={t('chat:session.close')}
            >
              ✕
            </button>
          </div>
        </div>
        {sessions.length === 0 ? (
          <div className="session-modal__empty muted">{t('chat:session.empty')}</div>
        ) : (
          <div className="session-modal__list">
            {sessions.map((row) => {
              const isActive = row.session_id === activeId;
              return (
                <div
                  key={row.session_id}
                  className={`session-modal__row${isActive ? ' session-modal__row--active' : ''}`}
                >
                  {renamingId === row.session_id ? (
                    <input
                      className="setting-input session-modal__rename"
                      value={renameDraft}
                      autoFocus
                      onChange={(e) => setRenameDraft(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') void handleRename(row.session_id);
                        if (e.key === 'Escape') {
                          // Cancel the rename only: preventDefault keeps the
                          // modal-level Escape handler from closing too
                          e.preventDefault();
                          setRenamingId('');
                        }
                      }}
                      onBlur={() => void handleRename(row.session_id)}
                    />
                  ) : (
                    <button
                      type="button"
                      className="session-modal__main"
                      disabled={busy}
                      onClick={() => void handleSwitch(row)}
                      title={t('chat:session.switch')}
                    >
                      <span className="session-modal__name">{row.title}</span>
                      <span className="small muted">
                        {t(`chat:session.status.${row.status}`, { defaultValue: row.status })}
                        {typeof row.turns === 'number' ? ` · ${row.turns}` : ''}
                      </span>
                    </button>
                  )}
                  <div className="session-modal__actions">
                    {isActive ? (
                      <span className="session-modal__badge">{t('chat:session.activeBadge')}</span>
                    ) : null}
                    <button
                      type="button"
                      className="btn btn-sm"
                      disabled={busy}
                      onClick={() => {
                        setRenamingId(row.session_id);
                        setRenameDraft(row.title);
                      }}
                    >
                      {t('chat:session.rename')}
                    </button>
                    <button
                      type="button"
                      className="btn btn-sm is-danger"
                      disabled={busy}
                      onClick={() => void handleDelete(row.session_id)}
                    >
                      {confirmingId === row.session_id
                        ? t('chat:session.deleteConfirm')
                        : t('chat:session.delete')}
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
        {status ? (
          <div className="session-modal__status small muted" role="status">
            {t('chat:session.context', {
              used: Math.round(status.used_tokens),
              pct: status.used_pct,
              threshold: status.auto_compact_at_pct,
            })}
            <button
              type="button"
              className="btn btn-sm"
              disabled={busy}
              onClick={() => void handleCompact()}
            >
              {t('chat:session.compact')}
            </button>
          </div>
        ) : null}
      </div>
    </ModalOverlay>
  );
}
