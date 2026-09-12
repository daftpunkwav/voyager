/**
 * @file AgentCharacterHead
 * @description SVG character heads per agent persona, with gaze-tracking eyes.
 *
 * Responsibilities:
 * - Map agent ids to six SVG head designs through the canonical id table
 * - Draw per-character features (hair, hats, glasses, accessories) around shared gaze eyes
 * - Fall back to the Hub head for unknown ids
 */
import type { FC } from 'react';
import { canonicalPersonaId } from '@/constants/personas';
import { Eye, GazeEyes, HeadSvgShell, type GazeOffset, type HeadSvgProps } from './shared';

interface AgentCharacterHeadProps extends HeadSvgProps {
  agentId: string;
}

/** Hub — conversation butler; a host wearing headphones. */
function HubHead({ look, isFocused }: HeadSvgProps) {
  return (
    <HeadSvgShell isFocused={isFocused}>
      <defs>
        <linearGradient id="hub-hair" x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#4a3aff" />
          <stop offset="100%" stopColor="#7c4dff" />
        </linearGradient>
      </defs>
      <ellipse cx="24" cy="27" rx="15" ry="14.5" fill="#f2d3c5" />
      <path d="M10 20 Q24 6 38 20 Q34 12 24 10 Q14 12 10 20Z" fill="url(#hub-hair)" />
      <path
        d="M8 22 Q8 14 14 12"
        stroke="#3d2eb8"
        strokeWidth="2.2"
        fill="none"
        strokeLinecap="round"
      />
      <path
        d="M40 22 Q40 14 34 12"
        stroke="#3d2eb8"
        strokeWidth="2.2"
        fill="none"
        strokeLinecap="round"
      />
      <rect x="7" y="20" width="4" height="8" rx="2" fill="#5e5ce6" />
      <rect x="37" y="20" width="4" height="8" rx="2" fill="#5e5ce6" />
      <GazeEyes left={{ x: 18, y: 25 }} right={{ x: 30, y: 25 }} look={look} />
      <path
        d="M19 33 Q24 37 29 33"
        stroke="#c47a62"
        strokeWidth="1.6"
        fill="none"
        strokeLinecap="round"
      />
      <circle cx="14" cy="30" r="2.2" fill="#ffb4a2" opacity="0.45" />
      <circle cx="34" cy="30" r="2.2" fill="#ffb4a2" opacity="0.45" />
    </HeadSvgShell>
  );
}

/** Scout — quick analysis; a scout in an explorer hat. */
function ScoutHead({ look, isFocused }: HeadSvgProps) {
  return (
    <HeadSvgShell isFocused={isFocused}>
      <ellipse cx="24" cy="28" rx="14.5" ry="14" fill="#ffd9b8" />
      <path d="M9 22 L24 10 L39 22 L36 24 L12 24Z" fill="#ff9f0a" />
      <path d="M24 10 L24 24" stroke="#e08600" strokeWidth="1" opacity="0.5" />
      <path
        d="M15 21 Q17 19 19 21"
        stroke="#8b5a2b"
        strokeWidth="1.4"
        fill="none"
        strokeLinecap="round"
      />
      <path
        d="M29 21 Q31 19 33 21"
        stroke="#8b5a2b"
        strokeWidth="1.4"
        fill="none"
        strokeLinecap="round"
      />
      <GazeEyes left={{ x: 18, y: 27 }} right={{ x: 30, y: 27 }} look={look} maxShift={2.8} />
      <path
        d="M20 34 Q24 36 28 34"
        stroke="#c47a62"
        strokeWidth="1.5"
        fill="none"
        strokeLinecap="round"
      />
      <circle cx="36" cy="18" r="2" fill="#ff6f00" opacity="0.8" />
    </HeadSvgShell>
  );
}

/** Mentor — in-depth explanations; a calm professor with glasses. */
function MentorHead({ look, isFocused }: HeadSvgProps) {
  return (
    <HeadSvgShell isFocused={isFocused}>
      <ellipse cx="24" cy="28" rx="15" ry="14.5" fill="#edd9f5" />
      <path d="M11 18 Q24 8 37 18 Q32 14 24 13 Q16 14 11 18Z" fill="#9d7abf" />
      <path
        d="M10 20 Q8 26 11 30"
        stroke="#7a5f96"
        strokeWidth="2.5"
        fill="none"
        strokeLinecap="round"
      />
      <path
        d="M38 20 Q40 26 37 30"
        stroke="#7a5f96"
        strokeWidth="2.5"
        fill="none"
        strokeLinecap="round"
      />
      <g stroke="#4a3f55" strokeWidth="1.5" fill="none">
        <circle cx="18" cy="26" r="5.5" />
        <circle cx="30" cy="26" r="5.5" />
        <path d="M23.5 26 L24.5 26" />
        <path d="M12.5 26 L12.5 28" />
        <path d="M35.5 26 L35.5 28" />
      </g>
      <Eye cx={18} cy={26} look={look} rx={3.2} ry={3.6} pupilR={1.7} maxShift={1.8} />
      <Eye cx={30} cy={26} look={look} rx={3.2} ry={3.6} pupilR={1.7} maxShift={1.8} />
      <path
        d="M22 35 Q24 36.5 26 35"
        stroke="#8b7355"
        strokeWidth="1.4"
        fill="none"
        strokeLinecap="round"
      />
      <path d="M22 37 L26 40 L30 37 Z" fill="#8b7355" opacity="0.75" />
    </HeadSvgShell>
  );
}

/** Navigator — learning planning; a navigator with an astrolabe on the forehead. */
function NavigatorHead({ look, isFocused }: HeadSvgProps) {
  return (
    <HeadSvgShell isFocused={isFocused}>
      <ellipse cx="24" cy="28" rx="14.5" ry="14" fill="#c8f2ef" />
      <path
        d="M11 20 Q24 11 37 20"
        stroke="#00b8d4"
        strokeWidth="3"
        fill="none"
        strokeLinecap="round"
      />
      <circle cx="24" cy="17" r="4" fill="#00d4aa" stroke="#0097a7" strokeWidth="1" />
      <path d="M24 14 L24 20 M21 17 L27 17" stroke="#fff" strokeWidth="1" strokeLinecap="round" />
      <path d="M13 22 Q15 20 17 22" stroke="#3d8b8b" strokeWidth="1.2" fill="none" />
      <path d="M31 22 Q33 20 35 22" stroke="#3d8b8b" strokeWidth="1.2" fill="none" />
      <GazeEyes left={{ x: 18, y: 27 }} right={{ x: 30, y: 27 }} look={look} />
      <path
        d="M19 34 Q24 37 29 34"
        stroke="#5ba89e"
        strokeWidth="1.5"
        fill="none"
        strokeLinecap="round"
      />
    </HeadSvgShell>
  );
}

/** Curator — organization butler; a librarian with a hair bun. */
function CuratorHead({ look, isFocused }: HeadSvgProps) {
  return (
    <HeadSvgShell isFocused={isFocused}>
      <ellipse cx="24" cy="29" rx="14" ry="13.5" fill="#d8f5e0" />
      <circle cx="24" cy="11" r="6.5" fill="#34c759" />
      <path d="M12 20 Q24 16 36 20" fill="#5cd685" />
      <g stroke="#2d6b42" strokeWidth="1.3" fill="none">
        <rect x="14" y="24" width="7" height="4" rx="1" />
        <rect x="27" y="24" width="7" height="4" rx="1" />
        <path d="M21 26 L27 26" />
      </g>
      <Eye cx={17.5} cy={27} look={look} rx={2.8} ry={3.2} pupilR={1.5} maxShift={1.6} />
      <Eye cx={30.5} cy={27} look={look} rx={2.8} ry={3.2} pupilR={1.5} maxShift={1.6} />
      <path
        d="M20 35 Q24 37 28 35"
        stroke="#5ba86e"
        strokeWidth="1.4"
        fill="none"
        strokeLinecap="round"
      />
    </HeadSvgShell>
  );
}

/** Scribe — note-taking assistant; a recorder with a pen behind the ear. */
function ScribeHead({ look, isFocused }: HeadSvgProps) {
  return (
    <HeadSvgShell isFocused={isFocused}>
      <ellipse cx="24" cy="28" rx="14.5" ry="14" fill="#ffe2ea" />
      <path d="M12 19 Q24 12 34 18 Q28 15 24 16 Q20 15 12 19Z" fill="#ff8fab" />
      <rect
        x="35"
        y="14"
        width="2.5"
        height="16"
        rx="1"
        fill="#ffd60a"
        transform="rotate(18 36 22)"
      />
      <polygon points="37,12 39,15 35,15" fill="#ff6b8a" transform="rotate(18 37 13)" />
      <GazeEyes left={{ x: 18, y: 27 }} right={{ x: 30, y: 27 }} look={look} />
      <path
        d="M19 34 Q24 36.5 29 34"
        stroke="#d4788f"
        strokeWidth="1.4"
        fill="none"
        strokeLinecap="round"
      />
      <circle cx="32" cy="32" r="1.2" fill="#5e5ce6" opacity="0.55" />
    </HeadSvgShell>
  );
}

const HEADS: Record<string, FC<HeadSvgProps>> = {
  orchestrator: HubHead,
  hub: HubHead,
  lucien: HubHead,
  recon: ScoutHead,
  scout: ScoutHead,
  navigator: NavigatorHead,
  iris: ScoutHead,
  explainer: MentorHead,
  mentor: MentorHead,
  elio: MentorHead,
  organizer: CuratorHead,
  curator: CuratorHead,
  scribe: ScribeHead,
  miyai: CuratorHead,
  graph_guide: NavigatorHead,
  atlas: NavigatorHead,
};

export function AgentCharacterHead({ agentId, look, isFocused }: AgentCharacterHeadProps) {
  const Head = HEADS[canonicalPersonaId(agentId)] ?? HubHead;
  return <Head look={look} isFocused={isFocused} />;
}

export type { GazeOffset };
