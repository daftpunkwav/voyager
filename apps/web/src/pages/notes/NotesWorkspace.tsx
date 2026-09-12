/**
 * @file NotesWorkspace
 * @description Notes workspace canvas: top bar, edit/preview split, and the TOC rail. Orchestration stays in NotesPage.
 *
 * Responsibilities:
 * - Compose the workspace: top bar, format bar host, editor/preview
 *   panes, and the TOC rail
 * - Render the split ratio, TOC width, and view mode from props, raising
 *   resize drags to the page
 */

import type { PointerEvent as ReactPointerEvent, ReactNode, Ref } from 'react';
import { useTranslation } from 'react-i18next';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { NoteEditor, type NoteEditorHandle } from './NoteEditor';
import { NotePreview } from './NotePreview';
import { TocPanel } from './NotesTocPanel';
import { NotesWorkspaceBar } from './NotesWorkspaceBar';
import { NOTES_TOC_WIDTH_MAX, NOTES_TOC_WIDTH_MIN, type NotesMode } from './notePrefs';
import type { NoteTocItem } from './noteOutline';

interface NotesWorkspaceProps {
  fontSize: number;
  mode: NotesMode;
  saveState: 'saved' | 'unsaved' | 'saving';
  persisted: boolean;
  pinned: boolean;
  archived: boolean;
  projectId: string;
  projectOptions: { value: string; label: string }[];
  syncScroll: boolean;
  tocOpen: boolean;
  tocItems: NoteTocItem[];
  tocWidth: number;
  splitRatio: number;
  showEdit: boolean;
  opening: boolean;
  workspaceReady: boolean;
  editMounted: boolean;
  previewMounted: boolean;
  editorTitle: string;
  previewBody: string;
  editingNoteId: string | null;
  formatBarHost: HTMLDivElement | null;
  saving: boolean;
  overlays: ReactNode;
  canvasRef: Ref<HTMLDivElement>;
  workspaceRef: Ref<HTMLDivElement>;
  onFormatBarHost: (el: HTMLDivElement | null) => void;
  onEditorReady: (api: NoteEditorHandle | null) => void;
  onPreviewEl: (el: HTMLDivElement | null) => void;
  onSplitPointerDown: (e: ReactPointerEvent<HTMLButtonElement>) => void;
  onTocPointerDown: (e: ReactPointerEvent<HTMLButtonElement>) => void;
  onTocWidth: (width: number) => void;
  onJumpToc: (item: NoteTocItem, headingId: string) => void;
  onBack: () => void;
  onNew: () => void;
  onMode: (mode: NotesMode) => void;
  onBumpFont: (delta: number) => void;
  onProject: (id: string) => void;
  onTogglePin: () => void;
  onToggleArchive: () => void;
  onToggleSync: () => void;
  onToggleToc: () => void;
  onAssist: () => void;
  onVersions: () => void;
  onExport: () => void;
  onDelete: () => void;
  onTrash: () => void;
  onSave: () => void;
}

export function NotesWorkspace({
  fontSize,
  mode,
  saveState,
  persisted,
  pinned,
  archived,
  projectId,
  projectOptions,
  syncScroll,
  tocOpen,
  tocItems,
  tocWidth,
  splitRatio,
  showEdit,
  opening,
  workspaceReady,
  editMounted,
  previewMounted,
  editorTitle,
  previewBody,
  editingNoteId,
  formatBarHost,
  saving,
  overlays,
  canvasRef,
  workspaceRef,
  onFormatBarHost,
  onEditorReady,
  onPreviewEl,
  onSplitPointerDown,
  onTocPointerDown,
  onTocWidth,
  onJumpToc,
  onBack,
  onNew,
  onMode,
  onBumpFont,
  onProject,
  onTogglePin,
  onToggleArchive,
  onToggleSync,
  onToggleToc,
  onAssist,
  onVersions,
  onExport,
  onDelete,
  onTrash,
  onSave,
}: NotesWorkspaceProps) {
  const { t } = useTranslation('notes');
  return (
    <div
      className="notes-shell notes-workspace-page"
      style={{ ['--notes-md-size' as string]: `${fontSize}px` }}
    >
      <NotesWorkspaceBar
        mode={mode}
        fontSize={fontSize}
        saveState={saveState}
        persisted={persisted}
        pinned={pinned}
        archived={archived}
        projectId={projectId}
        projectOptions={projectOptions}
        syncScroll={syncScroll}
        hasToc={tocItems.length > 0}
        tocOpen={tocOpen}
        onBack={onBack}
        onNew={onNew}
        onMode={onMode}
        onBumpFont={onBumpFont}
        onProject={onProject}
        onTogglePin={onTogglePin}
        onToggleArchive={onToggleArchive}
        onToggleSync={onToggleSync}
        onToggleToc={onToggleToc}
        onAssist={onAssist}
        onVersions={onVersions}
        onExport={onExport}
        onDelete={onDelete}
        onTrash={onTrash}
      />

      {showEdit && !(opening && !workspaceReady) ? (
        <div className="notes-format-bar" ref={onFormatBarHost} data-testid="notes-format-bar" />
      ) : null}

      <div className="notes-workspace" ref={workspaceRef}>
        <div
          ref={canvasRef}
          className={`notes-canvas is-${mode}`}
          style={
            mode === 'split'
              ? { ['--notes-edit-pct' as string]: `${Math.round(splitRatio * 1000) / 10}%` }
              : undefined
          }
        >
          {opening && !workspaceReady ? (
            <LoadingSpinner label={t('notes:workspace.opening')} />
          ) : (
            <>
              {editMounted && (
                <section className="edit-pane">
                  <div className="note-editor-wrap">
                    <NoteEditor
                      onSave={onSave}
                      saving={saving}
                      onReady={onEditorReady}
                      formatBarHost={formatBarHost}
                      visible={showEdit}
                    />
                  </div>
                </section>
              )}
              {mode === 'split' && (
                <button
                  type="button"
                  className="notes-split-handle"
                  aria-label={t('notes:workspace.splitHandleAria')}
                  onPointerDown={onSplitPointerDown}
                />
              )}
              {previewMounted && (
                <section className="preview-pane">
                  <NotePreview
                    title={editorTitle}
                    content={previewBody}
                    noteId={persisted ? editingNoteId : null}
                    inspectable={mode === 'preview'}
                    onScrollEl={onPreviewEl}
                  />
                </section>
              )}
            </>
          )}
        </div>
        {tocOpen && tocItems.length > 0 ? (
          <div
            className="notes-toc-wrap"
            style={{ ['--notes-toc-width' as string]: `${tocWidth}px` }}
          >
            <button
              type="button"
              className="notes-toc-handle"
              data-testid="notes-toc-handle"
              aria-label={t('notes:workspace.tocHandleAria')}
              aria-orientation="vertical"
              aria-valuemin={NOTES_TOC_WIDTH_MIN}
              aria-valuemax={NOTES_TOC_WIDTH_MAX}
              aria-valuenow={tocWidth}
              onPointerDown={onTocPointerDown}
              onKeyDown={(e) => {
                if (e.key === 'ArrowLeft') {
                  e.preventDefault();
                  onTocWidth(tocWidth + 16);
                } else if (e.key === 'ArrowRight') {
                  e.preventDefault();
                  onTocWidth(tocWidth - 16);
                }
              }}
            />
            <TocPanel items={tocItems} onJump={onJumpToc} />
          </div>
        ) : null}
      </div>
      {overlays}
    </div>
  );
}
