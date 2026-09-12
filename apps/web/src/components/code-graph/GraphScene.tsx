/**
 * @file GraphScene
 * @description R3F canvas composing the node cloud, edge lines, labels, tooltip
 * tracker, and bloom post-processing.
 *
 * Owns camera distance bounds, idle auto-rotation, camera fly-to animation,
 * and density-adaptive bloom thresholds for large graphs.
 *
 * Responsibilities:
 * - Compose the node cloud, edge lines, labels and tooltip tracker in one R3F canvas
 * - Own camera distance bounds, fly-to animation and idle auto-rotation
 * - Adapt bloom thresholds to graph density and theme the background
 * - Surface hover state and the shared camera-target computation
 */
import { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { Canvas, useThree, useFrame } from '@react-three/fiber';
import { OrbitControls } from '@react-three/drei';
import type { OrbitControls as OrbitControlsImpl } from 'three-stdlib';
import { EffectComposer, Bloom } from '@react-three/postprocessing';
import * as THREE from 'three';
import { NodeCloud } from './NodeCloud';
import { EdgeLines } from './EdgeLines';
import { NodeLabels } from './NodeLabels';
import { NodeTooltipContent, NodeTooltipTracker } from './NodeTooltip';
import type { CodeGraphData, CodeGraphNode } from './types';
import { useIsDarkTheme } from '@/hooks/useTheme';
import { BASE_AUTO_ROTATE_SPEED, computeAutoRotateSpeed, IDLE_ROTATE_MS } from './graphAutoRotate';
import {
  DEFAULT_DISPLAY_SETTINGS,
  BASE_NODE_GLOW,
  bloomIntensityScaleForGraph,
  nodeBoostScale,
  type DisplaySettings,
} from './density';

const BASE_BLOOM_INTENSITY = 0.525;
export const GRAPH_CANVAS_DPR: [number, number] = [1, 1.5];
export const GRAPH_COMPOSER_MULTISAMPLING = 0;

/** Shared distance bounds for OrbitControls and camera animations. */
export const CAMERA_MIN_DISTANCE = 20;
/** Engine layouts can span thousands of units, so leave plenty of zoom-out headroom. */
export const CAMERA_MAX_DISTANCE = 50000;

export interface CameraTarget {
  position: THREE.Vector3;
  lookAt: THREE.Vector3;
}

function clampCameraDistance(distance: number): number {
  return Math.min(CAMERA_MAX_DISTANCE, Math.max(CAMERA_MIN_DISTANCE, distance));
}

function CameraAnimator({
  target,
  controlsRef,
}: {
  target: CameraTarget | null;
  controlsRef: React.RefObject<OrbitControlsImpl | null>;
}) {
  const { camera } = useThree();
  const targetRef = useRef<CameraTarget | null>(null);
  const progress = useRef(1);

  useEffect(() => {
    if (target) {
      targetRef.current = target;
      progress.current = 0;
    }
  }, [target]);

  useFrame(() => {
    if (!targetRef.current || progress.current >= 1) return;
    progress.current = Math.min(1, progress.current + 0.02);
    const t = 1 - Math.pow(1 - progress.current, 3);
    camera.position.lerp(targetRef.current.position, t * 0.08);
    const controls = controlsRef.current;
    if (controls) {
      controls.target.lerp(targetRef.current.lookAt, t * 0.08);
      controls.update();
    } else {
      camera.lookAt(targetRef.current.lookAt);
    }
  });

  return null;
}

function IdleAutoRotate({
  controlsRef,
  idleMs = IDLE_ROTATE_MS,
}: {
  controlsRef: React.RefObject<OrbitControlsImpl | null>;
  idleMs?: number;
}) {
  const { camera } = useThree();
  const lastInteraction = useRef(Date.now());
  const resetTimer = useCallback(() => {
    lastInteraction.current = Date.now();
    if (controlsRef.current) controlsRef.current.autoRotate = false;
  }, [controlsRef]);

  useEffect(() => {
    const canvas = document.querySelector('.code-graph-canvas canvas');
    if (!canvas) return;
    canvas.addEventListener('pointerdown', resetTimer);
    canvas.addEventListener('wheel', resetTimer);
    return () => {
      canvas.removeEventListener('pointerdown', resetTimer);
      canvas.removeEventListener('wheel', resetTimer);
    };
  }, [resetTimer]);

  useFrame(() => {
    const controls = controlsRef.current;
    if (!controls) return;

    const idle = Date.now() - lastInteraction.current > idleMs;
    controls.autoRotate = idle;

    if (idle) {
      const dist = camera.position.distanceTo(controls.target);
      controls.autoRotateSpeed = computeAutoRotateSpeed(dist);
    }
  });

  return null;
}

interface GraphSceneProps {
  data: CodeGraphData;
  highlightedIds: Set<number> | null;
  cameraTarget: CameraTarget | null;
  showLabels: boolean;
  enableBloom: boolean;
  /** Idle time (ms) before auto-rotation kicks in. */
  idleRotateMs?: number;
  display?: DisplaySettings;
  onNodeClick: (node: CodeGraphNode) => void;
  onBackgroundClick?: () => void;
}

export function GraphScene({
  data,
  highlightedIds,
  cameraTarget,
  showLabels,
  enableBloom,
  idleRotateMs = IDLE_ROTATE_MS,
  display = DEFAULT_DISPLAY_SETTINGS,
  onNodeClick,
  onBackgroundClick,
}: GraphSceneProps) {
  const [hovered, setHovered] = useState<CodeGraphNode | null>(null);
  const controlsRef = useRef<OrbitControlsImpl | null>(null);
  const tooltipRef = useRef<HTMLDivElement | null>(null);
  const isDark = useIsDarkTheme();

  const bg = useMemo(() => {
    if (isDark) return '#06090f';
    /* Light theme uses an opaque Canvas background so edge/node contrast stays stable without relying on CSS layers underneath. */
    return '#eef2f7';
  }, [isDark]);

  const useBloom = enableBloom && isDark;
  /* Density-adaptive: node glow plus combined edge/node bloom, avoiding a blown-out white center at ~18k nodes / 80k edges. */
  const nodeBoost =
    BASE_NODE_GLOW * nodeBoostScale(data.nodes.length) * display.nodeGlow * (isDark ? 1 : 0.72);
  const bloomIntensity =
    BASE_BLOOM_INTENSITY *
    bloomIntensityScaleForGraph(data.nodes.length, data.edges.length) *
    display.bloom;
  /* Raise the bloom threshold at high density so overlapping edges/nodes are less likely to wash into a white blob. */
  const bloomThreshold = data.edges.length > 12000 || data.nodes.length > 8000 ? 0.52 : 0.35;

  // NodeCloud expects numeric ids; normalize numeric strings.
  const nodes = useMemo(
    () =>
      data.nodes.map((n) => ({
        ...n,
        id: typeof n.id === 'string' ? Number(n.id) || hashId(n.id) : n.id,
      })),
    [data.nodes]
  );
  const edges = useMemo(
    () =>
      data.edges.map((e) => ({
        ...e,
        source:
          typeof e.source === 'string' ? Number(e.source) || hashId(String(e.source)) : e.source,
        target:
          typeof e.target === 'string' ? Number(e.target) || hashId(String(e.target)) : e.target,
        type: e.type || e.relation || 'RELATED',
      })),
    [data.edges]
  );

  return (
    <div className="code-graph-canvas" style={{ width: '100%', height: '100%' }}>
      <div className="code-graph-tooltip-layer" aria-hidden={!hovered}>
        {hovered && (
          <div
            ref={tooltipRef}
            className="code-graph-tooltip code-graph-tooltip--screen"
            style={{ visibility: 'hidden' }}
          >
            <NodeTooltipContent node={hovered} />
          </div>
        )}
      </div>
      <Canvas
        key={isDark ? 'graph-dark' : 'graph-light'}
        camera={{ position: [0, 0, 800], fov: 50, near: 0.1, far: 100000 }}
        style={{ background: bg! }}
        dpr={GRAPH_CANVAS_DPR}
        gl={{
          antialias: false,
          alpha: false,
          powerPreference: 'high-performance',
        }}
        onPointerMissed={onBackgroundClick}
      >
        {bg && <color attach="background" args={[bg]} />}
        <ambientLight intensity={useBloom ? 0.5 : isDark ? 0.85 : 0.62} />
        <pointLight position={[500, 500, 500]} intensity={useBloom ? 0.6 : isDark ? 0.35 : 0.28} />
        <pointLight
          position={[-300, -200, -300]}
          intensity={useBloom ? 0.4 : isDark ? 0.2 : 0.18}
          color={useBloom ? '#6040ff' : isDark ? '#94a3b8' : '#94a3b8'}
        />

        <EdgeLines
          nodes={nodes as never}
          edges={edges as never}
          highlightedIds={highlightedIds}
          brightness={display.edgeBrightness}
          isDark={isDark}
        />
        <NodeCloud
          nodes={nodes as never}
          highlightedIds={highlightedIds}
          onHover={setHovered as never}
          onClick={onNodeClick as never}
          boost={nodeBoost}
          isDark={isDark}
        />
        {showLabels && (
          <NodeLabels nodes={nodes as never} highlightedIds={highlightedIds} isDark={isDark} />
        )}

        {hovered && <NodeTooltipTracker node={hovered as never} tooltipRef={tooltipRef} />}

        <CameraAnimator target={cameraTarget} controlsRef={controlsRef} />
        <IdleAutoRotate controlsRef={controlsRef} idleMs={idleRotateMs} />

        {useBloom && (
          <EffectComposer multisampling={GRAPH_COMPOSER_MULTISAMPLING}>
            <Bloom
              luminanceThreshold={bloomThreshold}
              luminanceSmoothing={0.7}
              intensity={bloomIntensity}
              mipmapBlur
              radius={0.6}
            />
          </EffectComposer>
        )}

        <OrbitControls
          ref={controlsRef}
          enableDamping
          dampingFactor={0.08}
          rotateSpeed={0.5}
          zoomSpeed={1.5}
          zoomToCursor
          minDistance={CAMERA_MIN_DISTANCE}
          maxDistance={CAMERA_MAX_DISTANCE}
          autoRotateSpeed={BASE_AUTO_ROTATE_SPEED}
        />
      </Canvas>
    </div>
  );
}

function hashId(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0;
  return Math.abs(h);
}

export function computeCameraTarget(nodes: CodeGraphNode[], ids: Set<number>): CameraTarget | null {
  if (ids.size === 0) return null;
  let cx = 0,
    cy = 0,
    cz = 0,
    count = 0;
  for (const node of nodes) {
    const id = typeof node.id === 'string' ? Number(node.id) : node.id;
    if (ids.has(id as number)) {
      cx += node.x;
      cy += node.y;
      cz += node.z;
      count++;
    }
  }
  if (count === 0) return null;
  cx /= count;
  cy /= count;
  cz /= count;
  let maxDist = 0;
  for (const node of nodes) {
    const id = typeof node.id === 'string' ? Number(node.id) : node.id;
    if (ids.has(id as number)) {
      const d = Math.sqrt((node.x - cx) ** 2 + (node.y - cy) ** 2 + (node.z - cz) ** 2);
      if (d > maxDist) maxDist = d;
    }
  }
  /* Frame at 3x the cluster radius, with a minimum distance for single nodes / small clusters. */
  const spreadDist = maxDist * 3;
  const minDist = count <= 5 ? 300 : count <= 12 ? 220 : 200;
  const distance = clampCameraDistance(Math.max(minDist, spreadDist));
  const lookAt = new THREE.Vector3(cx, cy, cz);
  const offset = new THREE.Vector3(0.2, 0.15, 1).normalize().multiplyScalar(distance);
  return {
    position: lookAt.clone().add(offset),
    lookAt,
  };
}
