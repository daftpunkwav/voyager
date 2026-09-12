/**
 * @file AgentAvatar
 * @description Character avatar whose eyes follow a gaze target on the page.
 *
 * Responsibilities:
 * - Compute gaze offsets from a page-space look target relative to the avatar box
 * - Track target movement via ResizeObserver and capture-phase scroll listeners
 * - Render the matching character head with idle blink and focus states
 */
import { useLayoutEffect, useRef, useState } from 'react';
import { AgentCharacterHead, type GazeOffset } from './avatars/AgentCharacterHead';

export interface LookTarget {
  x: number;
  y: number;
}

interface AgentAvatarProps {
  agentId: string;
  lookTarget: LookTarget | null;
  isFocused: boolean;
  size?: number;
  /** Bump to refresh the gaze direction when the carousel shifts. */
  gazeRevision?: number;
  /** Idle blinking animation. */
  blink?: boolean;
}

function computeGaze(avatarRect: DOMRect, target: LookTarget, isFocused: boolean): GazeOffset {
  if (isFocused) return { x: 0, y: 0 };

  const cx = avatarRect.left + avatarRect.width / 2;
  const cy = avatarRect.top + avatarRect.height * 0.44;
  const dx = target.x - cx;
  const dy = target.y - cy;
  const dist = Math.hypot(dx, dy) || 1;
  const strength = Math.min(1, 0.35 + dist / 280);
  return {
    x: (dx / dist) * strength,
    y: (dy / dist) * strength,
  };
}

export function AgentAvatar({
  agentId,
  lookTarget,
  isFocused,
  size = 54,
  gazeRevision = 0,
  blink = false,
}: AgentAvatarProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const [gaze, setGaze] = useState<GazeOffset>({ x: 0, y: 0 });

  useLayoutEffect(() => {
    const el = rootRef.current;
    if (!el || !lookTarget || isFocused) {
      setGaze({ x: 0, y: 0 });
      return;
    }

    const update = () => {
      if (!rootRef.current || !lookTarget) return;
      setGaze(computeGaze(rootRef.current.getBoundingClientRect(), lookTarget, false));
    };

    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    window.addEventListener('scroll', update, true);

    return () => {
      ro.disconnect();
      window.removeEventListener('scroll', update, true);
    };
  }, [lookTarget, isFocused, agentId, gazeRevision]);

  return (
    <div
      ref={rootRef}
      className={`agent-character${blink ? ' agent-character--blinking' : ''}`}
      style={{ width: size, height: size }}
      aria-hidden
    >
      <AgentCharacterHead agentId={agentId} look={gaze} isFocused={isFocused} />
    </div>
  );
}
