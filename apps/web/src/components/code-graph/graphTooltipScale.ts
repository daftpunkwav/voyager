/**
 * @file graphTooltipScale
 * @description Screen-space placement for the graph hover tooltip: distance
 * scaling, overlay inset measurement, and safe-area layout.
 *
 * Responsibilities:
 * - Scale the tooltip by camera distance and derive its anchor above the node
 * - Measure overlay insets (toolbar, panels, bars) that occlude the canvas
 * - Place the card in the safe area, flipping below the anchor when space runs out
 */
import type { GraphNode } from './types';

/** Typical browsing distance; scale = REF / dist (larger up close), clamped to [MIN, MAX]. */
export const TOOLTIP_REF_DISTANCE = 580;
/** Derivation: 0.78 x 1.1 x 1.1. */
export const TOOLTIP_MIN_SCALE = 0.9438;
/** Derivation: 1.06 x 1.3 x 1.1. */
export const TOOLTIP_MAX_SCALE = 1.5158;

/** Selectors of UI overlays that can cover the hover card (scoped to the graph stage / page). */
export const GRAPH_OVERLAY_SELECTORS = [
  '.graph-toolbar',
  '.node-detail:not(.is-collapsed)',
  '.graph-statusbar',
  '.graph-hint',
  '.code-graph-sidebar',
  '.code-graph-detail',
] as const;

export interface TooltipInsets {
  left: number;
  right: number;
  top: number;
  bottom: number;
}

export const EMPTY_TOOLTIP_INSETS: TooltipInsets = {
  left: 0,
  right: 0,
  top: 0,
  bottom: 0,
};

export function tooltipAnchorY(node: GraphNode): number {
  return node.y + Math.max(node.size, 2) * 1.1;
}

/** Zooming in makes the tooltip slightly larger, zooming out slightly smaller; clamped to the allowed range. */
export function computeTooltipScreenScale(distance: number): number {
  if (!Number.isFinite(distance) || distance <= 0) return 1;
  const raw = TOOLTIP_REF_DISTANCE / distance;
  return Math.min(TOOLTIP_MAX_SCALE, Math.max(TOOLTIP_MIN_SCALE, raw));
}

export interface TooltipScreenLayout {
  left: number;
  top: number;
  /** Whether the card is placed below the anchor (not enough room above). */
  placeBelow: boolean;
  transform: string;
}

function overlapAxis(a0: number, a1: number, b0: number, b1: number): number {
  return Math.max(0, Math.min(a1, b1) - Math.max(a0, b0));
}

/**
 * Accumulate the safe insets consumed by overlays (left toolbar, right detail
 * panel, bottom bars) from their intersection with the canvas.
 */
export function accumulateOverlayInset(
  canvas: {
    left: number;
    right: number;
    top: number;
    bottom: number;
    width: number;
    height: number;
  },
  overlay: {
    left: number;
    right: number;
    top: number;
    bottom: number;
    width: number;
    height: number;
  },
  insets: TooltipInsets
): void {
  const ix = overlapAxis(canvas.left, canvas.right, overlay.left, overlay.right);
  const iy = overlapAxis(canvas.top, canvas.bottom, overlay.top, overlay.bottom);
  if (ix <= 0 || iy <= 0) return;

  const midX = overlay.left + overlay.width / 2;
  const midY = overlay.top + overlay.height / 2;
  const canvasMidX = canvas.left + canvas.width / 2;
  const canvasMidY = canvas.top + canvas.height / 2;

  const isTall = iy > canvas.height * 0.28 || overlay.height >= overlay.width * 1.15;
  const isWide = ix > canvas.width * 0.28 || overlay.width >= overlay.height * 1.4;

  if (isTall && !isWide) {
    if (midX <= canvasMidX) {
      insets.left = Math.max(
        insets.left,
        Math.max(0, Math.min(overlay.right, canvas.right) - canvas.left)
      );
    } else {
      insets.right = Math.max(
        insets.right,
        Math.max(0, canvas.right - Math.max(overlay.left, canvas.left))
      );
    }
    return;
  }

  if (isWide && midY >= canvasMidY) {
    insets.bottom = Math.max(
      insets.bottom,
      Math.max(0, canvas.bottom - Math.max(overlay.top, canvas.top))
    );
    return;
  }

  if (isWide && midY < canvasMidY) {
    insets.top = Math.max(
      insets.top,
      Math.max(0, Math.min(overlay.bottom, canvas.bottom) - canvas.top)
    );
  }
}

/** Measure the insets that occluding overlays occupy relative to the canvas (pixels, canvas coordinates). */
export function measureGraphOverlayInsets(
  canvasEl: HTMLElement,
  selectors: readonly string[] = GRAPH_OVERLAY_SELECTORS
): TooltipInsets {
  const canvasRect = canvasEl.getBoundingClientRect();
  const insets: TooltipInsets = { ...EMPTY_TOOLTIP_INSETS };
  const root =
    canvasEl.closest('.graph-stage, .code-graph-page, .code-graph-layout') ??
    canvasEl.ownerDocument;

  for (const sel of selectors) {
    const nodes = root.querySelectorAll(sel);
    for (const node of nodes) {
      if (!(node instanceof HTMLElement)) continue;
      if (getComputedStyle(node).display === 'none') continue;
      const r = node.getBoundingClientRect();
      if (r.width < 4 || r.height < 4) continue;
      accumulateOverlayInset(canvasRect, r, insets);
    }
  }

  return insets;
}

/**
 * Place the hover card near the anchor, preferring above; flip below when
 * needed, and clamp to the safe area after subtracting overlay insets.
 * left/top is the card's top-left corner in the unscaled coordinate system,
 * paired with transform-origin: top left.
 */
export function layoutTooltipInViewport(opts: {
  anchorX: number;
  anchorY: number;
  boxW: number;
  boxH: number;
  viewW: number;
  viewH: number;
  scale: number;
  pad?: number;
  gap?: number;
  insets?: TooltipInsets;
}): TooltipScreenLayout {
  const pad = opts.pad ?? 8;
  const gap = opts.gap ?? 8;
  const scale = opts.scale;
  const w = Math.max(1, opts.boxW) * scale;
  const h = Math.max(1, opts.boxH) * scale;
  const insets = opts.insets ?? EMPTY_TOOLTIP_INSETS;

  const safeLeft = pad + insets.left;
  const safeTop = pad + insets.top;
  const safeRight = Math.max(safeLeft + w, opts.viewW - pad - insets.right);
  const safeBottom = Math.max(safeTop + h, opts.viewH - pad - insets.bottom);

  const spaceAbove = opts.anchorY - gap - h - safeTop;
  const spaceBelow = safeBottom - (opts.anchorY + gap + h);
  const placeBelow = spaceAbove < 0 && spaceBelow >= spaceAbove;

  let left = opts.anchorX - w / 2;
  let top = placeBelow ? opts.anchorY + gap : opts.anchorY - gap - h;

  /* Anchor inside the left overlay band: snap to the safe area's left edge instead of staying centered over the toolbar. */
  if (opts.anchorX < safeLeft + w * 0.35) {
    left = safeLeft;
  } else if (opts.anchorX > safeRight - w * 0.35) {
    left = safeRight - w;
  }

  const maxLeft = Math.max(safeLeft, safeRight - w);
  const maxTop = Math.max(safeTop, safeBottom - h);
  left = Math.min(maxLeft, Math.max(safeLeft, left));
  top = Math.min(maxTop, Math.max(safeTop, top));

  return {
    left,
    top,
    placeBelow,
    transform: `scale(${scale.toFixed(3)})`,
  };
}
