/**
 * @file TrendingSpotlight
 * @description Trending spotlight bubble on the overview page: agent avatar plus a streaming intro bubble for the highlighted repo.
 *
 * Responsibilities:
 * - Render the spotlight bubble per phase (hidden/visible/leaving) with
 *   avatar, gaze target, and streaming text
 * - Apply the width measured by the page so the bubble stays aligned
 */

import { useTranslation } from 'react-i18next';
import { AgentAvatar, type LookTarget } from '@/components/agent/AgentAvatar';
import { GLASS_CHIP } from '@/constants/glassTokens';
import type { TrendingRepo } from '@/api/types';
import type { TrendingSpotlightPhase } from '@/hooks/useTrendingSpotlight';
import type { CSSProperties } from 'react';

interface TrendingSpotlightProps {
  phase: TrendingSpotlightPhase;
  repo: TrendingRepo | null;
  content: string;
  isStreaming: boolean;
  lookTarget: LookTarget | null;
  bubbleWidthPx: number | null;
}

export function TrendingSpotlight({
  phase,
  repo,
  content,
  isStreaming,
  lookTarget,
  bubbleWidthPx,
}: TrendingSpotlightProps) {
  const { t } = useTranslation('overview');
  if (phase === 'hidden' || !repo) return null;

  const name = `${repo.owner}/${repo.repo}`;
  const bubbleStyle = bubbleWidthPx
    ? ({ '--scout-bubble-width': `${bubbleWidthPx}px` } as CSSProperties)
    : undefined;

  return (
    <div
      className={`trending-scout-spot trending-scout-spot--${phase}`}
      style={bubbleStyle}
      aria-live="polite"
      aria-label={t('overview:trending.spotlightAria', { name })}
    >
      <div className={`trending-scout-bubble overview-control-surface ${GLASS_CHIP}`}>
        <span className="trending-scout-bubble-label">Iris</span>
        <p className="trending-scout-bubble-text">
          {content}
          {isStreaming ? <span className="trending-scout-stream-cursor" aria-hidden /> : null}
        </p>
      </div>
      <AgentAvatar agentId="recon" lookTarget={lookTarget} isFocused={false} blink size={58} />
    </div>
  );
}
