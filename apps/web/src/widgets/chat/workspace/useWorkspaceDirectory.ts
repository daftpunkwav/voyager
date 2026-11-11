/**
 * @file useWorkspaceDirectory
 * @description Directory-listing state of the workspace chooser: the typed
 * path, the listing currently shown and the failure of the last load.
 *
 * Responsibilities:
 * - Load a directory listing through the workspace picker API
 * - Track the path input and the listing it navigates to
 * - Turn a failed load into the message the browser renders
 *
 * Constraints:
 * - The root listing is fetched once on mount; a later locale switch must not
 *   refetch it.
 * - Picker access stays behind the workspace API module.
 */

import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { type PickResult, pickDirectory } from '@/api/workspace';

/** Why the last listing failed; `unknown` covers a rejection that is not an Error. */
type DirectoryFailure =
  { readonly kind: 'message'; readonly message: string } | { readonly kind: 'unknown' };

export interface WorkspaceDirectory {
  /** Current content of the path input. */
  pathInput: string;
  /** Update the path input. */
  setPathInput: (value: string) => void;
  /** The listing currently shown; null before the first load settles. */
  current: PickResult | null;
  /** Message of the last failure; null when the last load succeeded. */
  failureMessage: string | null;
  /** Load the listing of a path and show it. */
  load: (path: string) => Promise<void>;
  /** Navigate to a path: the path input follows and its listing is loaded. */
  enter: (path: string) => void;
}

/** Directory-listing state of the workspace chooser. */
export function useWorkspaceDirectory(): WorkspaceDirectory {
  const { t } = useTranslation('chat');
  const [pathInput, setPathInput] = useState('');
  const [current, setCurrent] = useState<PickResult | null>(null);
  const [failure, setFailure] = useState<DirectoryFailure | null>(null);

  const load = useCallback(async (path: string) => {
    setFailure(null);
    try {
      const res = await pickDirectory(path);
      if (res.error) {
        setFailure({ kind: 'message', message: res.error.message });
        return;
      }
      setCurrent(res);
    } catch (err) {
      setFailure(
        err instanceof Error ? { kind: 'message', message: err.message } : { kind: 'unknown' }
      );
    }
  }, []);

  useEffect(() => {
    void load('');
  }, [load]);

  const enter = useCallback(
    (path: string) => {
      setPathInput(path);
      void load(path);
    },
    [load]
  );

  const failureMessage =
    failure === null
      ? null
      : failure.kind === 'message'
        ? failure.message
        : t('chat:workspace.loadFailed');

  return { pathInput, setPathInput, current, failureMessage, load, enter };
}
