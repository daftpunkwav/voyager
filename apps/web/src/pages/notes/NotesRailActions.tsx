/**
 * @file NotesRailActions
 * @description Notes-page primary actions: persona assist and new-note buttons, shared by the index page and the workspace, placed on the right.
 *
 * Responsibilities:
 * - Render the persona assist button with the resolved organizer display
 *   name and an accessible label
 * - Render the new-note primary action shared by both notes surfaces
 */

import { useTranslation } from 'react-i18next';
import { personaDisplayName } from '@/constants/personas';

export function NotesAssistButton({ onClick }: { onClick: () => void }) {
  const { t } = useTranslation('notes');
  const name = personaDisplayName('organizer');
  return (
    <button
      type="button"
      className="notes-rail-miyai liquid-glass liquid-glass--pill liquid-glass--green"
      aria-label={t('notes:rail.assistAria', { name })}
      data-testid="notes-assist-btn"
      onClick={onClick}
    >
      <span className="notes-rail-miyai__orb agent-organizer" aria-hidden />
      {name}
    </button>
  );
}

export function NotesNewButton({ onClick }: { onClick: () => void }) {
  const { t } = useTranslation('notes');
  return (
    <button
      type="button"
      className="btn btn-primary btn-sm notes-rail-new"
      onClick={onClick}
      data-testid="notes-new-btn"
    >
      {t('notes:action.new')}
    </button>
  );
}
