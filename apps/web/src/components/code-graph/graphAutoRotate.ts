/**
 * @file graphAutoRotate
 * @description Idle auto-rotation tuning: distance-compensated rotate speed
 * so the on-screen rotation feels constant at any zoom level.
 *
 * Responsibilities:
 * - Compute distance-compensated auto-rotate speed for constant on-screen rotation
 * - Publish the idle delay and speed constants shared with the graph scene
 */

/** Camera starts ~800 units from the target; this is the reference distance for on-screen angular speed. */
export const AUTO_ROTATE_REF_DISTANCE = 800;
export const BASE_AUTO_ROTATE_SPEED = 0.22;
export const AUTO_ROTATE_DIST_RATIO_MIN = 0.08;
export const AUTO_ROTATE_DIST_RATIO_MAX = 8;

/** Idle time (ms) before auto-rotation starts. */
export const IDLE_ROTATE_MS = 5_000;

/**
 * OrbitControls' autoRotateSpeed is a fixed angular speed, which looks faster
 * when zoomed in. Compensate proportionally to the camera-target distance so
 * the on-screen rotation feels roughly constant.
 */
export function computeAutoRotateSpeed(
  cameraDistance: number,
  refDistance = AUTO_ROTATE_REF_DISTANCE,
  baseSpeed = BASE_AUTO_ROTATE_SPEED
): number {
  if (!Number.isFinite(cameraDistance) || cameraDistance <= 0) return baseSpeed;
  const ratio = Math.min(
    AUTO_ROTATE_DIST_RATIO_MAX,
    Math.max(AUTO_ROTATE_DIST_RATIO_MIN, cameraDistance / refDistance)
  );
  return baseSpeed * ratio;
}
