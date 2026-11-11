/**
 * @file WorkspaceChip
 * @description Composer-bar workspace button: shows the current directory's
 * name; clicking opens the machine-wide directory chooser (drives/home
 * navigation) and hot-switches the agent (rebuild, no service restart)
 * through the shared workspaceSwitch bridge, which persists
 * agent.workspace.dir itself. The chooser renders through the shared
 * ModalOverlay (portaled to body) so composer backdrop-filter cannot clip it.
 *
 * The chooser itself lives next to this file under `workspace/`: the dialog,
 * its directory listing and the listing state.
 */

import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { callCapability } from '@/bridge/client';
import { switchWorkspaceWithMarker } from '@/bridge/workspaceSwitch';
import { ModalOverlay } from '@/components/common/ModalOverlay';
import { useChatStore } from '@/stores/chatStore';
import { confirmDialog, useUIStore } from '@/stores/uiStore';
import { WORKDIR_KEY } from '@/api/workspace';
import { WorkspaceBrowser } from '@/widgets/chat/workspace/WorkspaceBrowser';

/**
 * Workspace path button for the composer bar (bottom-left of the input):
 * shows the current directory's name only (full path in the tooltip); the
 * click opens the directory chooser to switch the workspace. Re-reads on
 * workspaceRev so cross-tab hot-switches stay fresh.
 */
export function WorkspacePathChip() {
  const { t } = useTranslation('chat');
  const workspaceRev = useChatStore((s) => s.workspaceRev);
  const [value, setValue] = useState('');
  const [browserOpen, setBrowserOpen] = useState(false);
  const [switching, setSwitching] = useState(false);

  useEffect(() => {
    let alive = true;
    callCapability<{ value?: unknown }>('settings', 'get_setting', { key: WORKDIR_KEY })
      .then((item) => {
        if (alive && typeof item?.value === 'string') setValue(item.value);
      })
      .catch(() => {}); // indicator hidden until a value arrives
    return () => {
      alive = false;
    };
  }, [workspaceRev]);

  if (!value) return null;
  // Current directory name only — parents stay out of the bar.
  const leaf = value.split(/[\\/]/).filter(Boolean).pop() ?? value;

  const pick = async (path: string) => {
    setBrowserOpen(false);
    const ok = await confirmDialog({ message: t('chat:workspace.switchConfirm') });
    if (!ok) return;
    setSwitching(true);
    try {
      const ws = await switchWorkspaceWithMarker(path);
      if (ws) setValue(ws);
    } catch (err) {
      useUIStore.getState().addToast({
        type: 'error',
        message: err instanceof Error ? err.message : t('chat:workspace.switchFailed'),
      });
    } finally {
      setSwitching(false);
    }
  };

  return (
    <>
      <button
        type="button"
        className="composer-ws"
        title={value}
        aria-label={`${t('chat:workspace.title')}: ${value}`}
        disabled={switching}
        onClick={() => setBrowserOpen(true)}
      >
        {leaf}
      </button>
      <ModalOverlay open={browserOpen} onClose={() => setBrowserOpen(false)}>
        <WorkspaceBrowser
          onPick={(path) => void pick(path)}
          onClose={() => setBrowserOpen(false)}
        />
      </ModalOverlay>
    </>
  );
}
