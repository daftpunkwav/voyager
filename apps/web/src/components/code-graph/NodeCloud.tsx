/**
 * @file NodeCloud
 * @description Node rendering for the graph: instanced glass spheres with halo
 * sprites, switching to point sprites for very large graphs.
 *
 * Responsibilities:
 * - Render nodes as instanced glass spheres with halo sprites in both themes
 * - Switch to point sprites with contrast-corrected colors for very large graphs
 * - Drive glass flow dynamics and halo alpha from camera distance each frame
 */
import { useEffect, useMemo, useRef } from 'react';
import { useFrame, useThree } from '@react-three/fiber';
import * as THREE from 'three';
import type { GraphNode } from './types';
import { nodeGlowBoost } from './density';
import { computeGlassDynamics, createGlassNodeMaterial } from './nodeGlassMaterial';

interface NodeCloudProps {
  nodes: GraphNode[];
  highlightedIds: Set<number> | null;
  onHover: (node: GraphNode | null) => void;
  onClick: (node: GraphNode) => void;
  opacity?: number;
  /* Multiplier on the per-node glow boost. 1 = full boost (sparse graphs),
   * 0 = flat colors (dense graphs). Adaptive default · user setting. */
  boost?: number;
  isDark?: boolean;
}

/* Above this count instanced spheres stop paying off (vertex + matrix cost)
 * and the cloud switches to point sprites — one position per node. */
const POINT_MODE_THRESHOLD = 75000;
/** Max node count for halos; disabled beyond this (point-sprite cost). */
const LIGHT_HALO_MAX_NODES = 8000;

function sphereDetail(count: number): [number, number, number] {
  if (count <= 8000) return [1, 32, 24];
  if (count <= 25000) return [1, 16, 12];
  return [1, 10, 7];
}

/** On light backgrounds, raise saturation and clamp over-bright colors to stay readable and reduce wash-out in dense regions. */
function ensureLightContrast(tempColor: THREE.Color, isDark: boolean): void {
  if (isDark) return;
  const hsl = { h: 0, s: 0, l: 0 };
  tempColor.getHSL(hsl);
  hsl.s = Math.min(1, hsl.s * 1.35 + 0.1);
  /* Tighten lightness: darker and more solid so dense spheres stop looking like white highlight blobs. */
  hsl.l = Math.min(0.48, Math.max(0.28, hsl.l * 0.78));
  if (hsl.h > 0.1 && hsl.h < 0.18) {
    hsl.l = Math.min(0.42, hsl.l);
    hsl.s = Math.min(1, hsl.s + 0.12);
  }
  tempColor.setHSL(hsl.h, hsl.s, hsl.l);
}

function nodeColor(
  node: GraphNode,
  highlightedIds: Set<number> | null,
  opacity: number,
  boost: number,
  tempColor: THREE.Color,
  isDark: boolean
): [number, number, number] {
  const hasHighlight = highlightedIds && highlightedIds.size > 0;
  tempColor.set(node.color);
  ensureLightContrast(tempColor, isDark);
  if (hasHighlight && !highlightedIds.has(node.id)) {
    tempColor.multiplyScalar(isDark ? 0.15 : 0.28);
  } else {
    const fullBoost = nodeGlowBoost(tempColor.r, tempColor.g, tempColor.b);
    const glowMix = isDark ? boost : Math.min(0.55, boost * 0.45);
    const applied = 1 + (fullBoost - 1) * glowMix;
    tempColor.multiplyScalar(applied);
  }
  return [tempColor.r * opacity, tempColor.g * opacity, tempColor.b * opacity];
}

let pointSprite: THREE.CanvasTexture | null = null;
function getPointSprite(): THREE.CanvasTexture {
  if (pointSprite) return pointSprite;
  const size = 64;
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext('2d')!;
  const gradient = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
  gradient.addColorStop(0, 'rgba(255,255,255,1)');
  gradient.addColorStop(0.45, 'rgba(255,255,255,0.85)');
  gradient.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, size, size);
  pointSprite = new THREE.CanvasTexture(canvas);
  return pointSprite;
}

/** Soft glow sprite for the light theme (solid center, fading edge). */
let glowSprite: THREE.CanvasTexture | null = null;
function getGlowSprite(): THREE.CanvasTexture {
  if (glowSprite) return glowSprite;
  const size = 128;
  const canvas = document.createElement('canvas');
  canvas.width = size;
  canvas.height = size;
  const ctx = canvas.getContext('2d')!;
  const c = size / 2;
  const gradient = ctx.createRadialGradient(c, c, 0, c, c, c);
  gradient.addColorStop(0, 'rgba(255,255,255,0.95)');
  gradient.addColorStop(0.22, 'rgba(255,255,255,0.55)');
  gradient.addColorStop(0.55, 'rgba(255,255,255,0.18)');
  gradient.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, size, size);
  glowSprite = new THREE.CanvasTexture(canvas);
  glowSprite.premultiplyAlpha = true;
  return glowSprite;
}

/* Light-theme halo shader with per-point size and per-point alpha.
 * PointsMaterial only supports global size/opacity, so large nodes cannot
 * get larger halos or highlighted nodes stronger ones. A custom
 * ShaderMaterial promotes size/alpha to per-vertex attributes in a single
 * draw call. */
let haloMaterialLight: THREE.ShaderMaterial | null = null;
let haloMaterialDark: THREE.ShaderMaterial | null = null;
function getHaloMaterial(isDark: boolean): THREE.ShaderMaterial {
  const cached = isDark ? haloMaterialDark : haloMaterialLight;
  if (cached) return cached;
  const mat = new THREE.ShaderMaterial({
    uniforms: {
      uMap: { value: getGlowSprite() },
      uScale: { value: 300 },
    },
    vertexShader: /* glsl */ `
      attribute vec3 aColor;
      attribute float aSize;
      attribute float aAlpha;
      varying vec3 vColor;
      varying float vAlpha;
      void main() {
        vColor = aColor;
        vAlpha = aAlpha;
        vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
        gl_PointSize = aSize * (uScale / -mvPosition.z);
        gl_Position = projectionMatrix * mvPosition;
      }
    `,
    fragmentShader: /* glsl */ `
      uniform sampler2D uMap;
      varying vec3 vColor;
      varying float vAlpha;
      void main() {
        vec4 tex = texture2D(uMap, gl_PointCoord);
        float a = tex.a * vAlpha;
        if (a < 0.01) discard;
        gl_FragColor = vec4(vColor * tex.rgb, a);
      }
    `,
    transparent: true,
    depthWrite: false,
    blending: isDark ? THREE.AdditiveBlending : THREE.NormalBlending,
    toneMapped: false,
  });
  if (isDark) haloMaterialDark = mat;
  else haloMaterialLight = mat;
  return mat;
}

function NodePoints({
  nodes,
  highlightedIds,
  onHover,
  onClick,
  opacity,
  boost,
  isDark,
}: Required<NodeCloudProps>) {
  const { raycaster } = useThree();

  useEffect(() => {
    const prev = raycaster.params.Points?.threshold ?? 1;
    raycaster.params.Points = { threshold: 3 };
    return () => {
      raycaster.params.Points = { threshold: prev };
    };
  }, [raycaster]);

  const { positions, colors } = useMemo(() => {
    const positions = new Float32Array(nodes.length * 3);
    const colors = new Float32Array(nodes.length * 3);
    const tempColor = new THREE.Color();
    for (let i = 0; i < nodes.length; i++) {
      const n = nodes[i];
      positions[i * 3] = n.x;
      positions[i * 3 + 1] = n.y;
      positions[i * 3 + 2] = n.z;
      const [r, g, b] = nodeColor(n, highlightedIds, opacity, boost, tempColor, isDark);
      colors[i * 3] = r;
      colors[i * 3 + 1] = g;
      colors[i * 3 + 2] = b;
    }
    return { positions, colors };
  }, [nodes, highlightedIds, opacity, boost, isDark]);

  return (
    <points
      key={nodes.length}
      onPointerOver={(e) => {
        e.stopPropagation();
        if (e.index !== undefined && e.index < nodes.length) {
          onHover(nodes[e.index]);
        }
      }}
      onPointerOut={() => onHover(null)}
      onClick={(e) => {
        e.stopPropagation();
        if (e.index !== undefined && e.index < nodes.length) {
          onClick(nodes[e.index]);
        }
      }}
    >
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
        <bufferAttribute attach="attributes-color" args={[colors, 3]} />
      </bufferGeometry>
      <pointsMaterial
        vertexColors
        size={isDark ? 6.5 : 7.5}
        sizeAttenuation
        map={getPointSprite()}
        alphaTest={0.28}
        transparent
        toneMapped={false}
      />
    </points>
  );
}

/** Per-node radial-gradient halos for both themes, simulating soft light sources. */
function NodeHalos({
  nodes,
  highlightedIds,
  isDark,
}: {
  nodes: GraphNode[];
  highlightedIds: Set<number> | null;
  isDark: boolean;
}) {
  const hasHighlight = Boolean(highlightedIds && highlightedIds.size > 0);

  const { positions, aColors, aSizes, aAlphas } = useMemo(() => {
    const positions = new Float32Array(nodes.length * 3);
    const aColors = new Float32Array(nodes.length * 3);
    const aSizes = new Float32Array(nodes.length);
    const aAlphas = new Float32Array(nodes.length);
    const tempColor = new THREE.Color();
    for (let i = 0; i < nodes.length; i++) {
      const n = nodes[i];
      positions[i * 3] = n.x;
      positions[i * 3 + 1] = n.y;
      positions[i * 3 + 2] = n.z;

      const isHL = !hasHighlight || (highlightedIds?.has(n.id) ?? false);

      tempColor.set(n.color);
      ensureLightContrast(tempColor, isDark);
      if (!isHL) {
        tempColor.multiplyScalar(isDark ? 0.08 : 0.12);
      } else if (!isDark) {
        tempColor.offsetHSL(0, 0.08, 0.18);
      } else {
        tempColor.offsetHSL(0, 0.06, 0.1);
      }
      aColors[i * 3] = tempColor.r;
      aColors[i * 3 + 1] = tempColor.g;
      aColors[i * 3 + 2] = tempColor.b;

      aSizes[i] = Math.max(8, (n.size || 4) * (isDark ? 6.4 : 7.2));
      aAlphas[i] = !hasHighlight ? (isDark ? 0.48 : 0.62) : isHL ? (isDark ? 0.72 : 0.82) : 0.1;
    }
    return { positions, aColors, aSizes, aAlphas };
  }, [nodes, highlightedIds, hasHighlight, isDark]);

  return (
    <points
      key={`halo-${nodes.length}-${isDark ? 'd' : 'l'}`}
      frustumCulled={false}
      raycast={() => null}
    >
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
        <bufferAttribute attach="attributes-aColor" args={[aColors, 3]} />
        <bufferAttribute attach="attributes-aSize" args={[aSizes, 1]} />
        <bufferAttribute attach="attributes-aAlpha" args={[aAlphas, 1]} />
      </bufferGeometry>
      <primitive object={getHaloMaterial(isDark)} attach="material" />
    </points>
  );
}

function NodeSpheres({
  nodes,
  highlightedIds,
  onHover,
  onClick,
  opacity,
  boost,
  isDark,
}: Required<NodeCloudProps>) {
  const meshRef = useRef<THREE.InstancedMesh>(null);
  const materialRef = useRef<THREE.ShaderMaterial | null>(null);
  const tempObj = useMemo(() => new THREE.Object3D(), []);
  const tempColor = useMemo(() => new THREE.Color(), []);
  const detail = sphereDetail(nodes.length);
  const { camera, controls } = useThree();
  const fallbackTarget = useMemo(() => new THREE.Vector3(0, 0, 0), []);

  const glassMat = useMemo(() => {
    const mat = createGlassNodeMaterial(isDark);
    materialRef.current = mat;
    return mat;
  }, [isDark]);

  useEffect(() => {
    return () => {
      glassMat.dispose();
    };
  }, [glassMat]);

  const avgSize = useMemo(() => {
    if (nodes.length === 0) return 4;
    let max = 0;
    for (const n of nodes) max = Math.max(max, n.size || 4);
    return max;
  }, [nodes]);

  const colors = useMemo(() => {
    const arr = new Float32Array(nodes.length * 3);
    for (let i = 0; i < nodes.length; i++) {
      const [r, g, b] = nodeColor(nodes[i], highlightedIds, opacity, boost, tempColor, isDark);
      arr[i * 3] = r;
      arr[i * 3 + 1] = g;
      arr[i * 3 + 2] = b;
    }
    return arr;
  }, [nodes, highlightedIds, tempColor, opacity, boost, isDark]);

  useEffect(() => {
    const mesh = meshRef.current;
    if (!mesh) return;

    const hasHighlight = highlightedIds && highlightedIds.size > 0;
    for (let i = 0; i < nodes.length; i++) {
      const n = nodes[i];
      tempObj.position.set(n.x, n.y, n.z);
      const isHighlighted = !hasHighlight || highlightedIds.has(n.id);
      /* Glass sphere core size shared by both themes (slightly reduced in dark to tame over-exposure). */
      const core = isHighlighted ? (isDark ? 0.84 : 0.88) : isDark ? 0.38 : 0.42;
      const s = n.size * core;
      tempObj.scale.set(s, s, s);
      tempObj.updateMatrix();
      mesh.setMatrixAt(i, tempObj.matrix);
    }
    mesh.instanceMatrix.needsUpdate = true;
    mesh.computeBoundingSphere();
  }, [nodes, highlightedIds, tempObj, isDark]);

  useFrame((_, delta) => {
    const mat = materialRef.current;
    if (!mat) return;
    const target =
      controls && 'target' in controls && controls.target
        ? (controls.target as THREE.Vector3)
        : fallbackTarget;
    const dist = camera.position.distanceTo(target);
    /* Judge by the largest node size: zooming into a hub turns the animation on sooner. */
    const dynamics = computeGlassDynamics(dist, avgSize);
    mat.uniforms.uDynamics.value = dynamics;
    /* Full-speed flow up close; a very slow crawl farther out keeps the static mottling visible. */
    const speed = dynamics > 0.01 ? 1.0 : dist < avgSize * 90 ? 0.25 : 0;
    if (speed > 0) {
      mat.uniforms.uTime.value += delta * speed;
    }
  });

  return (
    <instancedMesh
      key={`${nodes.length}-${isDark ? 'd' : 'l'}`}
      ref={meshRef}
      args={[undefined, undefined, nodes.length]}
      frustumCulled={false}
      onPointerOver={(e) => {
        e.stopPropagation();
        if (e.instanceId !== undefined && e.instanceId < nodes.length) {
          onHover(nodes[e.instanceId]);
        }
      }}
      onPointerOut={() => onHover(null)}
      onClick={(e) => {
        e.stopPropagation();
        if (e.instanceId !== undefined && e.instanceId < nodes.length) {
          onClick(nodes[e.instanceId]);
        }
      }}
    >
      <sphereGeometry args={detail} />
      <primitive object={glassMat} attach="material" />
      <instancedBufferAttribute attach="geometry-attributes-color" args={[colors, 3]} />
    </instancedMesh>
  );
}

export function NodeCloud({
  nodes,
  highlightedIds,
  onHover,
  onClick,
  opacity = 1.0,
  boost = 1.0,
  isDark = true,
}: NodeCloudProps) {
  const showHalos = nodes.length > 0 && nodes.length <= LIGHT_HALO_MAX_NODES;

  if (nodes.length > POINT_MODE_THRESHOLD) {
    return (
      <NodePoints
        nodes={nodes}
        highlightedIds={highlightedIds}
        onHover={onHover}
        onClick={onClick}
        opacity={opacity}
        boost={boost}
        isDark={isDark}
      />
    );
  }

  return (
    <group>
      {showHalos && <NodeHalos nodes={nodes} highlightedIds={highlightedIds} isDark={isDark} />}
      <NodeSpheres
        nodes={nodes}
        highlightedIds={highlightedIds}
        onHover={onHover}
        onClick={onClick}
        opacity={opacity}
        boost={boost}
        isDark={isDark}
      />
    </group>
  );
}
