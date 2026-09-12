/**
 * @file ProgressBadge
 * @description Small pill badge showing a project's learning progress state.
 */

import type { ProjectProgress } from '@/api/types';
import { progressLabel } from '@/utils/labels';

interface ProgressBadgeProps {
  progress: ProjectProgress;
}

/** Renders progress-pill + progress-{state} styling. */
export function ProgressBadge({ progress }: ProgressBadgeProps) {
  return <span className={`progress-pill progress-${progress}`}>{progressLabel(progress)}</span>;
}
