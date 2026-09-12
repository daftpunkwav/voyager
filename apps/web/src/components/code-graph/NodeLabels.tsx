/**
 * @file NodeLabels
 * @description Text labels for graph nodes, rendered as camera-facing sprites
 * with a distance-based budget and screen-space de-overlapping.
 *
 * Responsibilities:
 * - Render camera-facing text sprites with distance-tuned world font sizes
 * - Budget visible labels by camera distance and pick non-overlapping ones per frame
 * - Regenerate label textures when text or theme changes
 */
import { useEffect, useMemo, useRef } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import * as THREE from 'three';
import type { GraphNode } from './types';
import {
  labelBudgetForDistance,
  labelPriority,
  labelWorldFontSize,
  pickNonOverlappingLabels,
  shortenLabelName,
  type ProjectedLabel,
} from './labelLayout';

interface NodeLabelsProps {
  nodes: GraphNode[];
  highlightedIds: Set<number> | null;
  maxLabels?: number;
  isDark?: boolean;
}

interface LabelTexture {
  texture: THREE.CanvasTexture;
  width: number;
  height: number;
}

const TEXTURE_FONT_SIZE = 64;
const TEXTURE_FONT =
  `600 ${TEXTURE_FONT_SIZE}px Inter, system-ui, -apple-system, ` +
  'BlinkMacSystemFont, "Segoe UI", sans-serif';
const TEXTURE_MAX_TEXT_WIDTH = 560;
const TEXTURE_PADDING_X = 20;
const TEXTURE_PADDING_Y = 12;
const TEXTURE_STROKE_WIDTH = 7;
const LABEL_FILL_DARK = '#f1f5f9';
const LABEL_STROKE_DARK = 'rgba(0, 0, 0, 0.92)';
const LABEL_FILL_LIGHT = '#0f172a';
const LABEL_STROKE_LIGHT = 'rgba(255, 255, 255, 0.92)';

const _proj = new THREE.Vector3();
const _cluster = new THREE.Vector3();
const _nodePos = new THREE.Vector3();

function fitText(ctx: CanvasRenderingContext2D, text: string, maxWidth: number): string {
  if (ctx.measureText(text).width <= maxWidth) return text;

  let lo = 0;
  let hi = text.length;
  while (lo < hi) {
    const mid = Math.ceil((lo + hi) / 2);
    const candidate = `${text.slice(0, mid)}…`;
    if (ctx.measureText(candidate).width <= maxWidth) lo = mid;
    else hi = mid - 1;
  }

  return `${text.slice(0, Math.max(1, lo))}…`;
}

function createLabelTexture(name: string, isDark: boolean): LabelTexture | null {
  const canvas = document.createElement('canvas');
  const ctx = canvas.getContext('2d');
  if (!ctx) return null;

  ctx.font = TEXTURE_FONT;
  const text = fitText(ctx, name, TEXTURE_MAX_TEXT_WIDTH);
  const textWidth = Math.ceil(ctx.measureText(text).width);
  const logicalWidth = Math.max(1, textWidth + TEXTURE_PADDING_X * 2 + TEXTURE_STROKE_WIDTH * 2);
  const logicalHeight = TEXTURE_FONT_SIZE + TEXTURE_PADDING_Y * 2 + TEXTURE_STROKE_WIDTH * 2;
  const pixelRatio = typeof window === 'undefined' ? 1 : Math.min(window.devicePixelRatio || 1, 2);

  canvas.width = Math.ceil(logicalWidth * pixelRatio);
  canvas.height = Math.ceil(logicalHeight * pixelRatio);

  ctx.scale(pixelRatio, pixelRatio);
  ctx.font = TEXTURE_FONT;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.lineJoin = 'round';
  ctx.lineWidth = TEXTURE_STROKE_WIDTH;
  ctx.strokeStyle = isDark ? LABEL_STROKE_DARK : LABEL_STROKE_LIGHT;
  ctx.fillStyle = isDark ? LABEL_FILL_DARK : LABEL_FILL_LIGHT;

  const x = logicalWidth / 2;
  const y = logicalHeight / 2;
  ctx.strokeText(text, x, y);
  ctx.fillText(text, x, y);

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.minFilter = THREE.LinearFilter;
  texture.magFilter = THREE.LinearFilter;
  texture.generateMipmaps = false;
  texture.needsUpdate = true;

  return { texture, width: logicalWidth, height: logicalHeight };
}

function displayName(node: GraphNode): string {
  const raw = node.name || '';
  if ((node.kind === 'Project' || node.label === 'Project') && raw.includes('/')) {
    return raw.split('/').pop() || raw;
  }
  return shortenLabelName(raw);
}

type SpriteEntry = {
  node: GraphNode;
  sprite: THREE.Sprite;
  label: LabelTexture;
  priority: number;
};

function NodeLabelSprite({
  node,
  register,
  isDark,
}: {
  node: GraphNode;
  register: (id: number, entry: SpriteEntry | null) => void;
  isDark: boolean;
}) {
  const spriteRef = useRef<THREE.Sprite>(null);
  const text = displayName(node);
  const label = useMemo(() => createLabelTexture(text, isDark), [text, isDark]);
  const priority = useMemo(() => labelPriority(node), [node]);

  useEffect(() => {
    return () => label?.texture.dispose();
  }, [label]);

  useEffect(() => {
    const sprite = spriteRef.current;
    if (!sprite || !label) {
      register(node.id, null);
      return;
    }
    register(node.id, { node, sprite, label, priority });
    return () => register(node.id, null);
  }, [node, label, priority, register]);

  if (!label) return null;

  return (
    <sprite
      ref={spriteRef}
      position={[node.x, node.y + (node.size || 4) * 0.7, node.z]}
      scale={[1, 1, 1]}
      renderOrder={20}
      frustumCulled={false}
      visible={false}
    >
      <spriteMaterial
        map={label.texture}
        transparent
        depthWrite={false}
        depthTest
        toneMapped={false}
        opacity={0.92}
      />
    </sprite>
  );
}

function LabelOcclusion({
  entriesRef,
  maxLabels,
}: {
  entriesRef: React.MutableRefObject<Map<number, SpriteEntry>>;
  maxLabels: number;
}) {
  const { camera, size } = useThree();
  const frame = useRef(0);
  const scratch = useRef<ProjectedLabel[]>([]);

  useFrame(() => {
    frame.current += 1;
    /* No need to recompute every frame; ~10fps is enough while rotating. */
    if (frame.current % 3 !== 0) return;

    const entries = [...entriesRef.current.values()];
    if (entries.length === 0) return;

    let cx = 0;
    let cy = 0;
    let cz = 0;
    for (const e of entries) {
      cx += e.node.x;
      cy += e.node.y;
      cz += e.node.z;
    }
    const n = entries.length;
    _cluster.set(cx / n, cy / n, cz / n);
    const viewDist = camera.position.distanceTo(_cluster);
    const budget = labelBudgetForDistance(viewDist, maxLabels);

    const projected = scratch.current;
    projected.length = 0;

    for (const e of entries) {
      _proj.set(e.node.x, e.node.y, e.node.z).project(camera);
      if (_proj.z < -1 || _proj.z > 1) {
        e.sprite.visible = false;
        continue;
      }
      if (_proj.x < -1.15 || _proj.x > 1.15 || _proj.y < -1.15 || _proj.y > 1.15) {
        e.sprite.visible = false;
        continue;
      }

      _nodePos.set(e.node.x, e.node.y, e.node.z);
      const dist = camera.position.distanceTo(_nodePos);
      const worldFont = labelWorldFontSize(dist, e.node.size || 4);
      const worldH = worldFont * (e.label.height / TEXTURE_FONT_SIZE);
      const worldW = worldH * (e.label.width / e.label.height);
      e.sprite.position.set(e.node.x, e.node.y + (e.node.size || 4) * 0.7 + worldH / 2, e.node.z);
      e.sprite.scale.set(worldW, worldH, 1);

      /* Rough screen-pixel box estimated from world size (inversely proportional to distance). */
      const pxPerWorld = (size.height * 0.55) / Math.max(dist, 1);
      const screenW = Math.max(36, worldW * pxPerWorld);
      const screenH = Math.max(14, worldH * pxPerWorld);

      projected.push({
        id: e.node.id,
        x: (_proj.x * 0.5 + 0.5) * size.width,
        y: (-_proj.y * 0.5 + 0.5) * size.height,
        w: screenW,
        h: screenH,
        priority: e.priority,
      });
    }

    const keep = pickNonOverlappingLabels(projected, budget, 6);
    for (const e of entries) {
      e.sprite.visible = keep.has(e.node.id);
    }
  });

  return null;
}

export function NodeLabels({
  nodes,
  highlightedIds,
  maxLabels = 40,
  isDark = true,
}: NodeLabelsProps) {
  const entriesRef = useRef(new Map<number, SpriteEntry>());

  const register = useMemo(() => {
    return (id: number, entry: SpriteEntry | null) => {
      if (entry) entriesRef.current.set(id, entry);
      else entriesRef.current.delete(id);
    };
  }, []);

  const labeled = useMemo(() => {
    const hasHighlight = highlightedIds && highlightedIds.size > 0;

    if (hasHighlight) {
      return nodes
        .filter((n) => highlightedIds.has(n.id))
        .sort((a, b) => labelPriority(b) - labelPriority(a))
        .slice(0, Math.min(maxLabels, 28));
    }

    /* Candidate pool slightly larger than the budget; on-screen overlap picking trims it. */
    const pool = Math.min(maxLabels * 2, 64);
    return [...nodes].sort((a, b) => labelPriority(b) - labelPriority(a)).slice(0, pool);
  }, [nodes, highlightedIds, maxLabels]);

  return (
    <group>
      <LabelOcclusion entriesRef={entriesRef} maxLabels={maxLabels} />
      {labeled.map((node) => (
        <NodeLabelSprite
          key={`${node.id}-${isDark ? 'd' : 'l'}`}
          node={node}
          register={register}
          isDark={isDark}
        />
      ))}
    </group>
  );
}
