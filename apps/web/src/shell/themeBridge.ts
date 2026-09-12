/**
 * @file themeBridge.ts
 * @description Theme bridge with the backend appearance.theme as the single source of truth.
 *
 * This file is the only place that applies data-theme to the DOM (uiStore
 * never touches data-theme; font scale --font-scale is the exception and is
 * also written by uiStore):
 * - startup: get_theme -> applyTheme + write back to uiStore (avoiding
 *   dark-DOM / light-store dual-source drift);
 * - settings.changed (from user or agent) -> applyTheme + write back;
 * - system mode follows the OS prefers-color-scheme.
 * User toggles (Topbar / settings page) persist via set_theme first, then take
 * effect uniformly through this bridge.
 *
 * Responsibilities:
 * - Apply data-theme as the single DOM write point for theme (font-scale
 *   --font-scale is additionally written by uiStore)
 * - Sync the theme at startup, on OS scheme change and on settings.changed
 * - Expose resolveTheme so chart rendering stays consistent with the DOM
 */

import { useEffect } from 'react';
import { callCapability } from '@/bridge/client';
import { subscribe } from '@/bridge/stream';
import { useUIStore, type Theme } from '@/stores/uiStore';

interface ThemePayload {
  key?: string;
  value?: unknown;
}

/** Resolve the requested theme to the effective light|dark (system follows the OS); shared
 *  by the DOM application and chart components (MermaidBlock) to stay consistent with
 *  data-theme. */
export function resolveTheme(theme: string): 'light' | 'dark' {
  if (theme === 'system') {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }
  return theme === 'dark' ? 'dark' : 'light';
}

/** The only DOM theme application: always sets data-theme=light|dark (never removes the attribute). */
export function applyTheme(theme: string): void {
  const resolved = resolveTheme(theme);
  document.documentElement.dataset.theme = resolved;
  document.documentElement.dataset.themeRequested = theme;
}

/** Backend source of truth -> DOM + store selection, aligned in one step (shared by startup and hot updates). */
export function syncTheme(theme: string): void {
  applyTheme(theme);
  if (['light', 'dark', 'system'].includes(theme)) {
    useUIStore.getState().setTheme(theme as Theme);
  }
}

export function applyFontScale(scale: number): void {
  // Global font scaling via a CSS variable; body.style.zoom is avoided because it
  // causes blurry layout, offset positioning and pixel misalignment in some
  // browsers / high-DPI displays.
  document.documentElement.style.setProperty('--font-scale', String(scale));
}

export function useThemeBridge() {
  useEffect(() => {
    let alive = true;
    callCapability<{ theme: string; font_scale: number }>('settings', 'get_theme')
      .then((t) => {
        if (alive && t) {
          syncTheme(t.theme);
          applyFontScale(t.font_scale);
        }
      })
      .catch(() => {
        // Settings unreadable (e.g. backend not running): keep defaults, don't break shell rendering
      });

    const media = window.matchMedia('(prefers-color-scheme: dark)');
    const onSchemeChange = () => {
      // system mode follows the OS; this listener has no effect for other themes
      if (document.documentElement.dataset.themeRequested === 'system') {
        document.documentElement.dataset.theme = media.matches ? 'dark' : 'light';
      }
    };
    onSchemeChange();
    media.addEventListener('change', onSchemeChange);

    const off = subscribe(['settings.changed'], (event) => {
      const payload = event.payload as ThemePayload;
      if (payload.key === 'appearance.theme' && typeof payload.value === 'string') {
        syncTheme(payload.value);
      }
      if (payload.key === 'appearance.font_scale' && typeof payload.value === 'number') {
        applyFontScale(payload.value);
      }
    });

    return () => {
      alive = false;
      media.removeEventListener('change', onSchemeChange);
      off();
    };
  }, []);
}
