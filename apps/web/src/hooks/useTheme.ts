import { useSyncExternalStore } from 'react';
import { callCapability } from '@/bridge/client';
import { applyTheme } from '@/shell/themeBridge';
import { useUIStore } from '@/stores/uiStore';

/**
 * @file useTheme
 * @description Theme and font scaling. The backend (appearance.theme) is the
 * single source of truth: theme changes must persist via set_theme first
 * ('system' included), then update the UI selection and apply to the DOM
 * immediately without waiting for settings.changed, keeping it idempotent
 * under event replay. Selection state comes from the UI store, independent
 * of LLM settings.
 *
 * Responsibilities:
 * - Persist theme and font-scale changes via set_theme first ('system'
 *   included), then sync the store selection and DOM
 * - Expose changeTheme / changeFontScale; failures propagate so callers
 *   can toast without switching
 * - Report effective darkness via useIsDarkTheme, resolving 'system'
 *   against the OS prefers-color-scheme preference
 */
export function useTheme() {
  const theme = useUIStore((s) => s.theme);
  const fontScale = useUIStore((s) => s.fontScale);
  const setFontScale = useUIStore((s) => s.setFontScale);

  /** Change theme: persist to the backend first, then update selection and visuals; failures propagate to the caller. */
  const changeTheme = async (next: typeof theme) => {
    await callCapability('settings', 'set_theme', { theme: next });
    useUIStore.getState().setTheme(next);
    applyTheme(next);
  };

  /** Change font scale: persist via set_theme (the appearance capability that owns
   *  font_scale) first, then update the store (which applies the CSS var); failures
   *  propagate so the UI can toast. Note set_theme alone still emits settings.changed. */
  const changeFontScale = async (scale: number) => {
    await callCapability('settings', 'set_theme', { font_scale: scale });
    useUIStore.getState().setFontScale(scale);
  };

  return { theme, changeTheme, changeFontScale, fontScale, setFontScale };
}

function readSystemPrefersDark(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return false;
  }
  return window.matchMedia('(prefers-color-scheme: dark)').matches;
}

function subscribeSystemTheme(callback: () => void): () => void {
  const mq = window.matchMedia('(prefers-color-scheme: dark)');
  mq.addEventListener('change', callback);
  return () => mq.removeEventListener('change', callback);
}

/** Whether the dark appearance is active (including 'system' following the OS). */
export function useIsDarkTheme(): boolean {
  const theme = useUIStore((s) => s.theme);
  const systemDark = useSyncExternalStore(subscribeSystemTheme, readSystemPrefersDark, () => false);

  return theme === 'dark' || (theme === 'system' && systemDark);
}
