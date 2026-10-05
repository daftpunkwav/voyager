/**
 * @file ProjectProgressCard
 * @description Learning progress card of the project detail page (progress pills plus Miyai note-generation prompt).
 *
 * Responsibilities:
 * - Render the progress radio pills and raise changes to the coordinator
 * - Host the note-generation prompt bar for the organizer persona
 */
import type { Project, ProjectProgress } from '@/api/types';
import { useTranslation } from 'react-i18next';
import { GLASS_OUTER } from '@/constants/glassTokens';

const PD_PROGRESS: { id: ProjectProgress; className: string }[] = [
  { id: 'none', className: 'progress-none' },
  { id: 'learning', className: 'progress-learning' },
  { id: 'learned', className: 'progress-learned' },
  { id: 'mastered', className: 'progress-mastered' },
];

interface ProjectProgressCardProps {
  project: Project;
  /** Repo name shown in the Miyai prompt (repo name, falling back to project name) */
  scribeName: string;
  noteGenerating: boolean;
  /** Changes the learning progress (still routed through updateProgress.mutate on the coordinator page) */
  onProgressChange: (progress: ProjectProgress) => void;
  /** Generates a note (async; invoked with void inside the child) */
  onGenerateNote: () => void;
}

/** Learning progress card: progress radio pills plus the Miyai note-generation prompt bar */
export function ProjectProgressCard({
  project,
  scribeName,
  noteGenerating,
  onProgressChange,
  onGenerateNote,
}: ProjectProgressCardProps) {
  const { t } = useTranslation('sources');
  return (
    <div className={`pd-progress ${GLASS_OUTER}`}>
      <div className="pd-progress-head">
        <span className="label">{t('sources:progress.label')}</span>
      </div>
      <div
        className="pd-progress-list"
        role="radiogroup"
        aria-label={t('sources:progress.label')}
        onKeyDown={(e) => {
          if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
          e.preventDefault();
          const step = e.key === 'ArrowRight' ? 1 : -1;
          const at = PD_PROGRESS.findIndex((p) => p.id === project.progress);
          const next =
            PD_PROGRESS[(Math.max(at, 0) + step + PD_PROGRESS.length) % PD_PROGRESS.length];
          onProgressChange(next.id);
        }}
      >
        {PD_PROGRESS.map((p) => (
          <button
            key={p.id}
            type="button"
            role="radio"
            className={`pd-progress-pill ${p.className}`}
            aria-checked={project.progress === p.id ? 'true' : 'false'}
            onClick={() => onProgressChange(p.id)}
          >
            <span className="dot" />
            {t(`sources:progress.${p.id}`)}
          </button>
        ))}
      </div>
      <div className="pd-scribe-tip">
        <div className="tip-icon">
          <svg
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            width={16}
            height={16}
            aria-hidden="true"
          >
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
            <polyline points="14 2 14 8 20 8" />
          </svg>
        </div>
        <div className="pd-scribe-tip__body">
          <strong style={{ color: 'var(--chart-4)' }}>Miyai</strong>
          &nbsp;{t('sources:progress.tipPrefix')}
          <span className="mono">{scribeName}</span>
          {t('sources:progress.tipSuffix')}
        </div>
        <button
          type="button"
          className="btn btn-primary btn-sm pd-scribe-tip__btn"
          disabled={noteGenerating}
          onClick={() => void onGenerateNote()}
        >
          {noteGenerating ? t('sources:progress.generating') : t('sources:progress.generate')}
        </button>
      </div>
    </div>
  );
}
