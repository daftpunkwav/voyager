/**
 * @file shared
 * @description Shared building blocks for agent head SVGs: gaze-tracking eyes and the head shell.
 *
 * Responsibilities:
 * - Render eyes whose pupils shift by the normalized gaze offset (capped by maxShift)
 * - Provide the 48x48 head SVG shell with a focus modifier class
 */
import type { ReactNode } from 'react';

/** Gaze offset for the eyes, normalized to roughly -1..1. */
export interface GazeOffset {
  x: number;
  y: number;
}

interface EyeProps {
  cx: number;
  cy: number;
  look: GazeOffset;
  rx?: number;
  ry?: number;
  pupilR?: number;
  maxShift?: number;
}

export function Eye({ cx, cy, look, rx = 4.2, ry = 4.8, pupilR = 2.1, maxShift = 2.4 }: EyeProps) {
  const px = look.x * maxShift;
  const py = look.y * maxShift;
  return (
    <g transform={`translate(${cx} ${cy})`}>
      <g className="agent-eye">
        <ellipse cx={0} cy={0} rx={rx} ry={ry} fill="#fff" />
        <g className="agent-eye-pupil" transform={`translate(${px} ${py})`}>
          <circle cx={0} cy={0} r={pupilR} fill="#1d1d1f" />
          <circle cx={0.55} cy={-0.55} r={0.65} fill="#fff" opacity={0.92} />
        </g>
      </g>
    </g>
  );
}

interface GazeEyesProps {
  left: { x: number; y: number };
  right: { x: number; y: number };
  look: GazeOffset;
  maxShift?: number;
}

export function GazeEyes({ left, right, look, maxShift = 2.4 }: GazeEyesProps) {
  return (
    <>
      <Eye cx={left.x} cy={left.y} look={look} maxShift={maxShift} />
      <Eye cx={right.x} cy={right.y} look={look} maxShift={maxShift} />
    </>
  );
}

interface HeadSvgProps {
  look: GazeOffset;
  isFocused: boolean;
}

export function HeadSvgShell({ children, isFocused }: { children: ReactNode; isFocused: boolean }) {
  return (
    <svg
      viewBox="0 0 48 48"
      width="100%"
      height="100%"
      aria-hidden
      className={isFocused ? 'agent-head agent-head--focused' : 'agent-head'}
    >
      {children}
    </svg>
  );
}

export type { HeadSvgProps };
