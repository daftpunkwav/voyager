/**
 * @file NoteEditor
 * @description Markdown editor (a CodeMirror 6 wrapper): syntax highlighting, selection-wrapping toolbar, and paste-to-upload images.
 *
 * Configured via dependency injection rather than wrapping @uiw: the theme
 * reads CSS variables through EditorView.theme, so light/dark switches apply
 * instantly with data-theme and the font size follows --notes-md-size without
 * a reload. Pasted/dropped whitelisted images go uploadFile, then
 * notes.add_asset, then insert an attachment:// reference at the cursor.
 *
 * Responsibilities:
 * - Configure the CodeMirror 6 instance: CSS-variable theme, markdown
 *   language, history/line-number extensions, and imperative goToLine
 * - Render the format toolbar: inline formats, line prefixes, fences, and
 *   highlight tones applied over the document
 * - Handle whitelisted image paste/drop (upload + add_asset + insert the
 *   attachment reference)
 */

import { useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import { EditorState } from '@codemirror/state';
import { EditorView, highlightActiveLine, keymap, lineNumbers } from '@codemirror/view';
import {
  defaultKeymap,
  history,
  historyKeymap,
  indentWithTab,
  redo,
  undo,
} from '@codemirror/commands';
import { markdown, markdownLanguage } from '@codemirror/lang-markdown';
import { languages } from '@codemirror/language-data';
import { useNoteStore } from '@/stores/noteStore';
import { useUIStore } from '@/stores/uiStore';
import {
  applyNoteHighlightInDoc,
  diffReplace,
  NOTE_HL_LABEL,
  NOTE_HL_TONES,
  NOTES_HL_RGB_DEFAULT,
  NOTES_HL_RGB_KEY,
  type NoteHlAction,
} from './noteMarks';
import {
  emptyInlineInsert,
  toggleFenceInDoc,
  toggleInlineFormatInDoc,
  toggleLinePrefixBlock,
  type InlineFormat,
} from './noteFormat';

/** Aligned with the backend ALLOWED_EXTS; SVG excluded (can embed scripts). */
const NOTE_IMAGE_ACCEPT = 'image/png,image/jpeg,image/gif,image/webp';
const NOTE_IMAGE_MIMES = new Set([
  'image/png',
  'image/jpeg',
  'image/jpg',
  'image/gif',
  'image/webp',
]);
const NOTE_IMAGE_EXT = /\.(png|jpe?g|gif|webp)$/i;

export function isAllowedNoteImage(file: { type: string; name: string }): boolean {
  if (NOTE_IMAGE_MIMES.has(file.type)) return true;
  if (file.type.startsWith('image/')) return false;
  return NOTE_IMAGE_EXT.test(file.name);
}

export interface NoteEditorHandle {
  scrollDom: HTMLElement;
  goToLine: (line: number) => void;
}

interface NoteEditorProps {
  onSave: () => void;
  saving?: boolean;
  onReady?: (api: NoteEditorHandle | null) => void;
  /** Host the format bar above the split pane so both panes' content start at the same height. */
  formatBarHost?: HTMLElement | null;
  /** Stays mounted (CSS-hidden) in preview mode; requestMeasure after showing avoids a zero-height CodeMirror. */
  visible?: boolean;
}

/** Editor theme: font size via CSS variable; light/dark switch with zero reloads. */
const markdownTheme = EditorView.theme(
  {
    '&': {
      color: 'var(--text-1)',
      backgroundColor: 'transparent',
      fontSize: 'var(--notes-md-size, 15px)',
      height: '100%',
    },
    '.cm-content': {
      caretColor: 'var(--accent, #0a84ff)',
      fontFamily: 'var(--font-mono, ui-monospace, monospace)',
      lineHeight: '1.7',
      padding: '8px 16px 32px 4px',
      maxWidth: 'none',
    },
    '.cm-scroller': {
      overflow: 'auto',
      fontFamily: 'inherit',
    },
    '.cm-cursor, .cm-dropCursor': { borderLeftColor: 'var(--accent, #0a84ff)' },
    '&.cm-focused .cm-selectionBackground, .cm-selectionBackground, .cm-content ::selection': {
      backgroundColor: 'rgba(10, 132, 255, 0.18)',
    },
    '.cm-activeLine': { backgroundColor: 'rgba(120, 120, 128, 0.08)' },
    '.cm-gutters': {
      backgroundColor: 'transparent',
      color: 'var(--text-3)',
      border: 'none',
    },
  },
  { dark: false }
);

function wrapHighlightSelection(view: EditorView | null, action: NoteHlAction) {
  if (!view) return;
  const { from, to } = view.state.selection.main;
  if (from === to) return;
  const doc = view.state.doc.toString();
  const next = applyNoteHighlightInDoc(doc, from, to, action);
  if (next === doc) return;
  const patch = diffReplace(doc, next);
  view.dispatch({
    changes: { from: patch.from, to: patch.to, insert: patch.insert },
    selection: { anchor: patch.from, head: patch.from + patch.insert.length },
  });
  view.focus();
}

function applyDocChange(view: EditorView, next: string, selectFrom: number, selectTo: number) {
  const doc = view.state.doc.toString();
  if (next === doc) return;
  const patch = diffReplace(doc, next);
  view.dispatch({
    changes: { from: patch.from, to: patch.to, insert: patch.insert },
    selection: { anchor: selectFrom, head: selectTo },
    scrollIntoView: true,
  });
  view.focus();
}

function wrapSelection(view: EditorView | null, kind: InlineFormat) {
  if (!view) return;
  const { from, to } = view.state.selection.main;
  const doc = view.state.doc.toString();
  if (from === to) {
    const { insert, cursor } = emptyInlineInsert(kind);
    view.dispatch({
      changes: { from, insert },
      selection: { anchor: from + cursor },
      scrollIntoView: true,
    });
    view.focus();
    return;
  }
  const { from: a, to: b, next } = toggleInlineFormatInDoc(doc, from, to, kind);
  applyDocChange(view, next, a, a + (next.length - (doc.length - (b - a))));
}

function wrapFence(view: EditorView | null) {
  if (!view) return;
  const { from, to } = view.state.selection.main;
  const doc = view.state.doc.toString();
  if (from === to) {
    view.dispatch({
      changes: { from, insert: '```\n\n```' },
      selection: { anchor: from + 4 },
      scrollIntoView: true,
    });
    view.focus();
    return;
  }
  const { from: a, to: b, next } = toggleFenceInDoc(doc, from, to);
  applyDocChange(view, next, a, a + (next.length - (doc.length - (b - a))));
}

function toggleLinePrefix(view: EditorView | null, prefix: string) {
  if (!view) return;
  const { from, to } = view.state.selection.main;
  const startLine = view.state.doc.lineAt(from);
  const endLine = view.state.doc.lineAt(to);
  const a = startLine.from;
  const b = endLine.to;
  const doc = view.state.doc.toString();
  const next = doc.slice(0, a) + toggleLinePrefixBlock(doc.slice(a, b), prefix) + doc.slice(b);
  applyDocChange(view, next, a, a + (next.length - (doc.length - (b - a))));
}

function insertSnippet(view: EditorView | null, insert: string) {
  if (!view) return;
  const { from, to } = view.state.selection.main;
  view.dispatch({
    changes: { from, to, insert },
    selection: { anchor: from + insert.length },
    scrollIntoView: true,
  });
  view.focus();
}

function goToLine(view: EditorView, line: number) {
  const doc = view.state.doc;
  const n = Math.min(Math.max(1, line), doc.lines);
  const pos = doc.line(n).from;
  view.dispatch({ selection: { anchor: pos }, scrollIntoView: true });
  view.focus();
}

function Ico({ d }: { d: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden
    >
      <path d={d} />
    </svg>
  );
}

export function NoteEditor({
  onSave,
  saving,
  onReady,
  formatBarHost,
  visible = true,
}: NoteEditorProps) {
  const { t } = useTranslation('notes');
  const title = useNoteStore((s) => s.editorTitle);
  const content = useNoteStore((s) => s.editorContent);
  const setTitle = useNoteStore((s) => s.setEditorTitle);
  const setContent = useNoteStore((s) => s.setEditorContent);
  const addToast = useUIStore((s) => s.addToast);
  const viewRef = useRef<EditorView | null>(null);
  const hostRef = useRef<HTMLDivElement | null>(null);
  const applyingExternalRef = useRef(false);
  const [uploading, setUploading] = useState(false);
  const [tip, setTip] = useState<{ text: string; x: number; y: number } | null>(null);
  const [rgbHex, setRgbHex] = useState(() => {
    try {
      const raw = localStorage.getItem(NOTES_HL_RGB_KEY)?.replace('#', '').toLowerCase() ?? '';
      return /^[0-9a-f]{6}$/.test(raw) ? raw : NOTES_HL_RGB_DEFAULT;
    } catch {
      return NOTES_HL_RGB_DEFAULT;
    }
  });
  const onSaveRef = useRef(onSave);
  onSaveRef.current = onSave;
  const onReadyRef = useRef(onReady);
  onReadyRef.current = onReady;

  const wordCount = useMemo(() => content.replace(/\s/g, '').length, [content]);

  const showTip = (text: string, el: HTMLElement) => {
    const r = el.getBoundingClientRect();
    setTip({ text, x: r.left + r.width / 2, y: r.bottom });
  };

  const uploadImages = async (files: File[]) => {
    const allowed = files.filter(isAllowedNoteImage);
    if (allowed.length === 0) {
      addToast({ type: 'error', message: t('notes:toast.unsupportedImage') });
      return;
    }
    const view = viewRef.current;
    setUploading(true);
    try {
      for (const file of allowed) {
        const { uploadFile } = await import('@/bridge/client');
        const { file_path, filename } = await uploadFile(file);
        // api/notes.addAsset already unwraps the legacy envelope semantics (unwrapDataField); the return value is the business payload
        const payload = (await (await import('@/api/notes')).addAsset(file_path, filename)) as {
          markdown?: string;
          url?: string;
        } | null;
        const md =
          payload?.markdown ?? (payload?.url ? `![](${payload.url})` : `![](${String(payload)})`);
        if (view) {
          view.dispatch(view.state.replaceSelection(`\n${md}\n`));
          view.focus();
        } else {
          // Functional update: when looping over multiple images, content is a stale render-time closure value and direct concatenation would overwrite siblings
          setContent((prev) => prev + md);
        }
      }
    } catch (err) {
      addToast({
        type: 'error',
        message: err instanceof Error ? err.message : t('notes:toast.uploadFailed'),
      });
    } finally {
      setUploading(false);
    }
  };

  const uploadImagesRef = useRef(uploadImages);
  uploadImagesRef.current = uploadImages;
  const addToastRef = useRef(addToast);
  addToastRef.current = addToast;

  useEffect(() => {
    if (!hostRef.current) return;
    const state = EditorState.create({
      doc: content,
      extensions: [
        history(),
        lineNumbers(),
        highlightActiveLine(),
        keymap.of([...defaultKeymap, ...historyKeymap, indentWithTab]),
        markdown({ base: markdownLanguage, codeLanguages: languages }),
        markdownTheme,
        EditorView.lineWrapping,
        EditorView.updateListener.of((update) => {
          if (update.docChanged && !applyingExternalRef.current) {
            setContent(update.state.doc.toString());
          }
        }),
        keymap.of([
          {
            key: 'Mod-s',
            preventDefault: true,
            run: () => {
              onSaveRef.current();
              return true;
            },
          },
          {
            key: 'Mod-b',
            preventDefault: true,
            run: (view) => {
              wrapSelection(view, 'strong');
              return true;
            },
          },
          {
            key: 'Mod-i',
            preventDefault: true,
            run: (view) => {
              wrapSelection(view, 'em');
              return true;
            },
          },
        ]),
        EditorView.domEventHandlers({
          paste: (event) => {
            const files = Array.from(event.clipboardData?.files ?? []);
            const images = files.filter(isAllowedNoteImage);
            const hadImage = files.some(
              (f) => f.type.startsWith('image/') || isAllowedNoteImage(f)
            );
            if (!hadImage) return false;
            event.preventDefault();
            if (images.length === 0) {
              addToastRef.current({ type: 'error', message: t('notes:toast.unsupportedImage') });
              return true;
            }
            void uploadImagesRef.current(images);
            return true;
          },
          drop: (event) => {
            const files = Array.from(event.dataTransfer?.files ?? []);
            const images = files.filter(isAllowedNoteImage);
            const hadImage = files.some(
              (f) => f.type.startsWith('image/') || isAllowedNoteImage(f)
            );
            if (!hadImage) return false;
            event.preventDefault();
            if (images.length === 0) {
              addToastRef.current({ type: 'error', message: t('notes:toast.unsupportedImage') });
              return true;
            }
            void uploadImagesRef.current(images);
            return true;
          },
        }),
      ],
    });
    const view = new EditorView({ state, parent: hostRef.current });
    viewRef.current = view;
    onReadyRef.current?.({
      scrollDom: view.scrollDOM,
      goToLine: (line) => goToLine(view, line),
    });
    return () => {
      onReadyRef.current?.(null);
      view.destroy();
      viewRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!visible) return;
    viewRef.current?.requestMeasure();
  }, [visible]);

  useEffect(() => {
    const view = viewRef.current;
    if (!view) return;
    const current = view.state.doc.toString();
    if (current === content) return;
    const patch = diffReplace(current, content);
    applyingExternalRef.current = true;
    try {
      const fullReplace = patch.from === 0 && patch.to === current.length;
      view.dispatch({
        changes: { from: patch.from, to: patch.to, insert: patch.insert },
        // Switching notes: cursor back to the top; partial patch: let CM map the selection itself so the insertion point survives
        ...(fullReplace ? { selection: { anchor: 0 }, scrollIntoView: true } : {}),
      });
    } finally {
      applyingExternalRef.current = false;
    }
  }, [content]);

  const btn = (
    label: string,
    onClick: () => void,
    child: ReactNode,
    extra = '',
    btnKey?: string
  ) => (
    <button
      key={btnKey}
      type="button"
      className={`edit-toolbar-btn${extra ? ` ${extra}` : ''}`}
      aria-label={label}
      onMouseEnter={(e) => showTip(label, e.currentTarget)}
      onMouseLeave={() => setTip(null)}
      onClick={onClick}
    >
      {child}
    </button>
  );

  const toolbar = (
    <div className="edit-toolbar">
      {btn(
        t('notes:editor.undo'),
        () => {
          const v = viewRef.current;
          if (v) undo(v);
        },
        <Ico d="M9 14l-4-4 4-4M5 10h11a4 4 0 010 8h-1" />
      )}
      {btn(
        t('notes:editor.redo'),
        () => {
          const v = viewRef.current;
          if (v) redo(v);
        },
        <Ico d="M15 14l4-4-4-4M19 10H8a4 4 0 000 8h1" />
      )}
      <div className="edit-toolbar-divider" />
      {btn(
        t('notes:editor.bold'),
        () => wrapSelection(viewRef.current, 'strong'),
        <strong>B</strong>,
        'bold'
      )}
      {btn(t('notes:editor.italic'), () => wrapSelection(viewRef.current, 'em'), <em>I</em>)}
      {NOTE_HL_TONES.map((tone) =>
        btn(
          t(`notes:${NOTE_HL_LABEL[tone]}`),
          () => wrapHighlightSelection(viewRef.current, tone),
          <span className={`edit-toolbar-hl edit-toolbar-hl--${tone}`} />,
          `hl hl-${tone}`,
          tone
        )
      )}
      <label
        className="edit-toolbar-btn hl hl-rgb"
        aria-label={t('notes:editor.customHighlight')}
        onMouseEnter={(e) => showTip(t('notes:editor.customHighlight'), e.currentTarget)}
        onMouseLeave={() => setTip(null)}
      >
        <span className="edit-toolbar-hl" style={{ background: `#${rgbHex}` }} />
        <input
          type="color"
          className="edit-toolbar-rgb"
          value={`#${rgbHex}`}
          aria-label={t('notes:editor.pickCustomColor')}
          onChange={(e) => {
            const hex = e.target.value.replace('#', '').toLowerCase();
            setRgbHex(hex);
            try {
              localStorage.setItem(NOTES_HL_RGB_KEY, hex);
            } catch {
              /* Storage unavailable: still apply the highlight rather than blocking it */
            }
            wrapHighlightSelection(viewRef.current, `rgb${hex}`);
          }}
          onClick={(e) => e.stopPropagation()}
        />
      </label>
      {btn(
        t('notes:editor.clearHighlight'),
        () => wrapHighlightSelection(viewRef.current, 'clear'),
        <span className="edit-toolbar-hl edit-toolbar-hl--clear" />,
        'hl'
      )}
      {btn(
        t('notes:editor.inlineCode'),
        () => wrapSelection(viewRef.current, 'code'),
        <Ico d="M16 18l6-6-6-6M8 6l-6 6 6 6" />,
        'code'
      )}
      {btn(
        t('notes:editor.link'),
        () => wrapSelection(viewRef.current, 'link'),
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          aria-hidden
        >
          <path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71" />
          <path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71" />
        </svg>
      )}
      <div className="edit-toolbar-divider" />
      {btn(t('notes:editor.heading'), () => toggleLinePrefix(viewRef.current, '## '), 'H')}
      {btn(
        t('notes:editor.quote'),
        () => toggleLinePrefix(viewRef.current, '> '),
        <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden>
          <path d="M7 17h4l2-4V7H5v6h4zm8 0h4l2-4V7h-8v6h4z" />
        </svg>
      )}
      {btn(
        t('notes:editor.bulletList'),
        () => toggleLinePrefix(viewRef.current, '- '),
        <Ico d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" />
      )}
      {btn(
        t('notes:editor.taskList'),
        () => toggleLinePrefix(viewRef.current, '- [ ] '),
        <Ico d="M9 11l3 3L22 4M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11" />
      )}
      <div className="edit-toolbar-divider" />
      {btn(
        t('notes:editor.codeBlock'),
        () => wrapFence(viewRef.current),
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          aria-hidden
        >
          <polyline points="16 18 22 12 16 6" />
          <polyline points="8 6 2 12 8 18" />
        </svg>
      )}
      {btn(
        t('notes:editor.table'),
        () => insertSnippet(viewRef.current, t('notes:editor.tableSnippet')),
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
          <rect x="3" y="3" width="18" height="18" rx="2" />
          <path d="M3 9h18M3 15h18M9 3v18" />
        </svg>
      )}
      {btn(
        t('notes:editor.strikethrough'),
        () => wrapSelection(viewRef.current, 'strike'),
        <s>S</s>
      )}
      {btn(
        t('notes:editor.divider'),
        () => insertSnippet(viewRef.current, '\n---\n'),
        <Ico d="M4 12h16" />
      )}
      <div className="edit-toolbar-divider" />
      {btn(
        uploading ? t('notes:editor.uploading') : t('notes:editor.insertImage'),
        () => {
          const input = document.createElement('input');
          input.type = 'file';
          input.accept = NOTE_IMAGE_ACCEPT;
          input.onchange = () => {
            if (input.files) void uploadImages(Array.from(input.files));
          };
          input.click();
        },
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden>
          <rect x="3" y="3" width="18" height="18" rx="2" />
          <circle cx="8.5" cy="8.5" r="1.5" />
          <path d="M21 15l-5-5L5 21" />
        </svg>
      )}
      <div className="edit-toolbar-divider" />
      <button
        type="button"
        className="btn btn-primary btn-sm"
        data-testid="save-note-btn"
        style={{ marginLeft: 'auto' }}
        onClick={onSave}
        disabled={saving}
      >
        {saving ? t('notes:editor.saving') : t('notes:editor.save')}
      </button>
      <span className="muted" style={{ fontFamily: 'var(--font-mono)', fontSize: 11 }}>
        {t('notes:charCount', { n: wordCount })}
      </span>
    </div>
  );

  return (
    <div className="note-editor">
      {formatBarHost
        ? createPortal(toolbar, formatBarHost)
        : formatBarHost === undefined
          ? toolbar
          : null}
      {tip
        ? createPortal(
            <div className="notes-toolbar-tip" style={{ left: tip.x, top: tip.y }} role="tooltip">
              {tip.text}
            </div>,
            document.body
          )
        : null}
      <input
        className="edit-title-input"
        value={title}
        onChange={(e) => setTitle(e.target.value)}
        placeholder={t('notes:editor.untitledPlaceholder')}
      />
      <div
        className="edit-content-area edit-content-area--cm"
        ref={hostRef}
        data-testid="note-editor-cm"
      />
    </div>
  );
}
