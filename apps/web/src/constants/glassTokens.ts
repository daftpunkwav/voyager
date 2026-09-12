/**
 * @file glassTokens
 * @description Liquid-glass layer tokens; class strings map one-to-one to
 * liquid-glass.css.
 *
 * Three semantic layers: outer panel / inner interactive pill controls /
 * inner small non-interactive chips. Per-scene differences (radius, spacing)
 * are overridden by each page's CSS, not duplicated here as constants.
 */

/** Outer layer - panel-level glass (0.05 tint / blur 10px / no inner glow). */
export const GLASS_OUTER = 'glass-card glass-card--overview-outer';

/** Inner layer - interactive pill controls (0.1 tint / blur 50px / inner glow + hover state). */
export const GLASS_INNER =
  'overview-control-surface glass-card glass-card--overview-inner liquid-glass--pill liquid-glass--interactive';

/** Inner layer - non-interactive small widgets (avatars/badges/rank chips; radius set by consumer CSS). */
export const GLASS_CHIP = 'glass-card glass-card--overview-inner';
