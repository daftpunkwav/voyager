/**
 * @file UsagePage
 * @description Standalone LLM usage page rendering the usage dashboard full-screen.
 */

import { LlmUsageDashboard } from '@/components/usage/LlmUsageDashboard';

export function UsagePage() {
  return (
    <div className="usage-page page-scaffold">
      <div className="page-scaffold__body">
        <LlmUsageDashboard />
      </div>
    </div>
  );
}
