/**
 * @file nodeGlassMaterial
 * @description Glass/pigment ShaderMaterial for graph node spheres, with a
 * time-driven flow animation that activates near the camera.
 *
 * Responsibilities:
 * - Build the glass ShaderMaterial (vertex + fragment GLSL) for node spheres
 * - Animate pigment flow from time and camera-proximity uniforms
 * - Compute the dynamics factor from camera distance and the max node size
 */
import * as THREE from 'three';

/**
 * Dynamics enablement threshold: the glass flows noticeably when the camera
 * is closer than the node feature size times this factor. A larger factor
 * means the dynamics show up from farther away (triggers more easily).
 */
export const GLASS_DYNAMICS_DIST_FACTOR = 55;

const VERT = /* glsl */ `
attribute vec3 color;
varying vec3 vColor;
varying vec3 vWorldNormal;
varying vec3 vViewDir;
varying vec3 vLocalPos;

void main() {
  vColor = color;
  vLocalPos = position;
  vec4 worldPos = modelMatrix * instanceMatrix * vec4(position, 1.0);
  vec3 transformedNormal = normalMatrix * mat3(instanceMatrix) * normal;
  vWorldNormal = normalize(transformedNormal);
  vec4 mvPosition = viewMatrix * worldPos;
  vViewDir = normalize(-mvPosition.xyz);
  gl_Position = projectionMatrix * mvPosition;
}
`;

const FRAG = /* glsl */ `
uniform float uTime;
uniform float uDynamics;
uniform float uIsDark;

varying vec3 vColor;
varying vec3 vWorldNormal;
varying vec3 vViewDir;
varying vec3 vLocalPos;

float hash(vec3 p) {
  p = fract(p * 0.3183099 + vec3(0.1, 0.2, 0.3));
  p *= 17.0;
  return fract(p.x * p.y * p.z * (p.x + p.y + p.z));
}

float noise(vec3 p) {
  vec3 i = floor(p);
  vec3 f = fract(p);
  f = f * f * (3.0 - 2.0 * f);
  float n000 = hash(i);
  float n100 = hash(i + vec3(1.0, 0.0, 0.0));
  float n010 = hash(i + vec3(0.0, 1.0, 0.0));
  float n110 = hash(i + vec3(1.0, 1.0, 0.0));
  float n001 = hash(i + vec3(0.0, 0.0, 1.0));
  float n101 = hash(i + vec3(1.0, 0.0, 1.0));
  float n011 = hash(i + vec3(0.0, 1.0, 1.0));
  float n111 = hash(i + vec3(1.0, 1.0, 1.0));
  float nx00 = mix(n000, n100, f.x);
  float nx10 = mix(n010, n110, f.x);
  float nx01 = mix(n001, n101, f.x);
  float nx11 = mix(n011, n111, f.x);
  float nxy0 = mix(nx00, nx10, f.y);
  float nxy1 = mix(nx01, nx11, f.y);
  return mix(nxy0, nxy1, f.z);
}

float fbm(vec3 p) {
  float v = 0.0;
  float a = 0.5;
  for (int i = 0; i < 3; i++) {
    v += a * noise(p);
    p = p * 2.03 + vec3(0.1, -0.2, 0.15);
    a *= 0.5;
  }
  return v;
}

void main() {
  vec3 N = normalize(vWorldNormal);
  vec3 V = normalize(vViewDir);
  float fresnel = pow(1.0 - max(dot(N, V), 0.0), 2.2);

  /* Large pigment blobs: low-frequency noise, must read with depth even when static */
  float flow = uTime * (0.15 + uDynamics * 0.85);
  vec3 pigmentCoord = vLocalPos * 1.15 + vec3(flow * 0.35, -flow * 0.22, flow * 0.18);
  float blob = fbm(pigmentCoord);
  float vein = fbm(pigmentCoord * 2.4 + vec3(2.0, flow, -1.0));
  float pigmentMix = clamp(blob * 0.72 + vein * 0.38, 0.0, 1.0);

  /* Widen the density contrast: lighter areas lighter, deeper areas deeper */
  float density = mix(0.42, 1.35, pigmentMix);
  density = mix(density, mix(0.32, 1.45, pigmentMix), uDynamics);

  vec3 pigment = vColor * density;
  /* Tint light spots toward glass white to reinforce the pigment-in-water layering */
  pigment = mix(pigment, mix(vColor, vec3(1.0), 0.35), (1.0 - pigmentMix) * 0.25);

  /* Liquid glass shell (shared look across themes; darker theme dials it back to avoid blowout) */
  float glassMix = mix(0.28, 0.18, uIsDark);
  vec3 glassTint = mix(pigment, vec3(1.0), glassMix * fresnel);
  vec3 rim = vec3(1.0) * fresnel * mix(0.7, 0.55, uIsDark);
  vec3 col = glassTint * (0.72 + 0.28 * (1.0 - fresnel)) + rim;

  float spec = pow(max(dot(N, normalize(V + vec3(0.25, 0.85, 0.35))), 0.0), 36.0);
  col += vec3(1.0) * spec * mix(0.65, 0.5, uIsDark);

  /* Subtle edge shimmer while animated, signaling motion */
  col += vColor * fresnel * uDynamics * 0.12 * (0.5 + 0.5 * sin(uTime * 2.5));

  float alpha = mix(0.94, 0.72, fresnel * 0.55);
  gl_FragColor = vec4(col, alpha);
}
`;

export function createGlassNodeMaterial(isDark: boolean): THREE.ShaderMaterial {
  return new THREE.ShaderMaterial({
    uniforms: {
      uTime: { value: 0 },
      uDynamics: { value: 0 },
      uIsDark: { value: isDark ? 1 : 0 },
    },
    vertexShader: VERT,
    fragmentShader: FRAG,
    transparent: true,
    depthWrite: true,
    toneMapped: false,
  });
}

/**
 * Estimated from the largest node in the scene: zooming into a big sphere
 * turns the animation on sooner. Larger maxNodeSize / smaller distance
 * means higher dynamics.
 */
export function computeGlassDynamics(cameraDistance: number, maxNodeSize: number): number {
  if (!Number.isFinite(cameraDistance) || cameraDistance <= 1) return 0;
  const size = Math.max(2, maxNodeSize);
  const ratio = (size * GLASS_DYNAMICS_DIST_FACTOR) / cameraDistance;
  if (ratio < 0.35) return 0;
  if (ratio > 1.1) return 1;
  return (ratio - 0.35) / (1.1 - 0.35);
}
