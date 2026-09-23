/**
 * @file uiStore.ts
 * @description Global UI state: theme selection, sidebar collapse, font scale,
 * toasts, and modal depth (for layered Esc handling). Persisted via zustand
 * persist with a storage-key migration.
 *
 * Responsibilities:
 * - Hold shell-wide state: theme and locale selections, sidebar collapse,
 *   font scale (clamped and applied as a CSS variable), toasts, modal depth
 * - Persist the selection subset via zustand persist under a migrated
 *   storage key
 * - Count open global modals (push/pop paired) so page-level Esc handling
 *   can yield while a modal is up
 *
 * This module must not depend on UI-layer components.
 */
import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { STORAGE, migrateKey } from '@/brand';
import type { LocaleChoice } from '@/i18n/types';

migrateKey(STORAGE.uiStore, STORAGE.legacy.uiStore);

export type Theme = 'dark' | 'light' | 'system';

export interface Toast {
  id: string;
  type: 'success' | 'error' | 'warning' | 'info';
  message: string;
  /** Error code, for rendering and lookup */
  code?: string;
  duration?: number;
}

/** Payload for the global imperative confirm dialog (window.confirm replacement). */
export interface ConfirmRequest {
  /** Headline; falls back to the shared "confirm" title when omitted */
  title?: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  /** Style the confirm action as destructive */
  danger?: boolean;
}

interface UIState {
  theme: Theme;
  /** Locale *selection* ('system' included); the effective language is resolved
   *  and applied only by shell/localeBridge (never here — locale/theme selection
   *  touches no DOM; font scale is the exception and writes --font-scale). */
  locale: LocaleChoice;
  sidebarCollapsed: boolean;
  fontScale: number;
  toasts: Toast[];
  /** Count of currently open global modals (lightbox etc.); when > 0, page-level Esc handling yields first (e.g. notes back to list) */
  modalDepth: number;
  /** Active imperative confirm request (null when no dialog is up) */
  confirmRequest: ConfirmRequest | null;
  confirmResolve: ((ok: boolean) => void) | null;
  setTheme: (theme: Theme) => void;
  setLocale: (locale: LocaleChoice) => void;
  toggleSidebar: () => void;
  setFontScale: (scale: number) => void;
  addToast: (toast: Omit<Toast, 'id'>) => void;
  removeToast: (id: string) => void;
  pushModal: () => void;
  popModal: () => void;
  /** Raise the global confirm dialog; resolves once the user answers. A newer
   *  request supersedes an unanswered one and settles it as cancelled. */
  confirm: (request: ConfirmRequest) => Promise<boolean>;
  resolveConfirm: (ok: boolean) => void;
}

export const useUIStore = create<UIState>()(
  persist(
    (set, get) => ({
      // The single source of truth for the theme is the backend appearance.theme; this
      // store only holds the UI selection, kept in sync by shell/themeBridge via
      // get_theme / settings.changed. The theme DOM data-theme is applied only by
      // themeBridge.applyTheme (font scale is the exception: setFontScale and
      // rehydration write --font-scale directly).
      theme: 'system',
      // Same relationship as theme: the backend appearance.locale is the single
      // source of truth; shell/localeBridge keeps this selection in sync.
      locale: 'zh-CN',
      sidebarCollapsed: false,
      fontScale: 1.0,
      toasts: [],
      modalDepth: 0,
      confirmRequest: null,
      confirmResolve: null,

      setTheme: (theme) => {
        set({ theme });
      },

      setLocale: (locale) => {
        set({ locale });
      },

      toggleSidebar: () => {
        set((state) => ({ sidebarCollapsed: !state.sidebarCollapsed }));
      },

      setFontScale: (scale) => {
        const clamped = Math.max(0.8, Math.min(1.5, scale));
        set({ fontScale: clamped });
        document.documentElement.style.setProperty('--font-scale', String(clamped));
      },

      addToast: (toast) => {
        const id = `toast_${Date.now()}_${Math.random().toString(36).slice(2, 7)}`;
        const newToast: Toast = { ...toast, id };
        set((state) => ({ toasts: [...state.toasts, newToast] }));
      },

      removeToast: (id) => {
        set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) }));
      },

      // Modal open/close counter (push/pop must be paired; components call these in effects).
      // Basis for layered Esc back-off: with a modal open, the page's own Esc shortcut yields first.
      pushModal: () => {
        set((state) => ({ modalDepth: state.modalDepth + 1 }));
      },

      popModal: () => {
        set((state) => ({ modalDepth: Math.max(0, state.modalDepth - 1) }));
      },

      confirm: (request) => {
        // Supersede any unanswered request so its awaiter never hangs.
        get().confirmResolve?.(false);
        return new Promise<boolean>((resolve) => {
          set({ confirmRequest: request, confirmResolve: resolve });
        });
      },

      resolveConfirm: (ok) => {
        get().confirmResolve?.(ok);
        set({ confirmRequest: null, confirmResolve: null });
      },
    }),
    {
      name: STORAGE.uiStore,
      partialize: (state) => ({
        theme: state.theme,
        locale: state.locale,
        sidebarCollapsed: state.sidebarCollapsed,
        fontScale: state.fontScale,
      }),
      onRehydrateStorage: () => (state) => {
        if (state) {
          document.documentElement.style.setProperty('--font-scale', String(state.fontScale));
        }
      },
    }
  )
);

/** Imperative confirm: Promise-based window.confirm replacement, rendered by
 *  the shell-mounted ConfirmDialogHost through the shared glass dialog. */
export function confirmDialog(request: ConfirmRequest): Promise<boolean> {
  return useUIStore.getState().confirm(request);
}
