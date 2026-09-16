/**
 * @file workspaceSwitchMarker
 * @description Unit tests for the workspace-switch marker caller contract:
 * every surface that hot-switches the workspace on an SSE-subscribed tab
 * must stash a request marker in chatStore before the POST (the broadcast
 * races the HTTP response), or its own tab sees the misleading
 * "switched elsewhere" toast. Covers the settings WorkspaceBlock surface;
 * the composer chip's useWorkspaceSwitch follows the same protocol.
 */

import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { callCapabilityMock } = vi.hoisted(() => ({ callCapabilityMock: vi.fn() }));

vi.mock('@/bridge/client', () => ({ callCapability: callCapabilityMock }));

import { WorkspaceBlock } from '@/components/settings/agent/WorkspaceBlock';
import { useChatStore } from '@/stores/chatStore';
import { useUIStore } from '@/stores/uiStore';
import { initI18n } from '@/i18n';

describe('WorkspaceBlock switch stashes the marker before the POST', () => {
  it('generates a marker, stashes it, and sends it on the switch request', async () => {
    callCapabilityMock.mockResolvedValue({ value: 'old-ws' });
    let switchUrl = '';
    let switchBody: string | undefined;
    vi.stubGlobal('crypto', { randomUUID: () => 'marker-settings-1' });
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        if (url === '/api/workspace/switch') {
          switchUrl = url;
          switchBody = init?.body;
        }
        return { ok: true, json: async () => ({ workspace: 'next-ws' }) } as Response;
      })
    );
    vi.spyOn(window, 'confirm').mockReturnValue(true);

    render(<WorkspaceBlock />);
    const input = await screen.findByLabelText('工作目录');
    fireEvent.change(input, { target: { value: 'next-ws' } });
    fireEvent.blur(input);

    await vi.waitFor(() => expect(switchUrl).toBe('/api/workspace/switch'));
    const body = JSON.parse(switchBody ?? '{}') as { dir?: string; marker?: string };
    expect(body.dir).toBe('next-ws');
    // The marker must be stashed (before the POST) and echoed on the wire.
    expect(body.marker).toBe('marker-settings-1');
    expect(useChatStore.getState().workspaceSwitchMarker).toBe('marker-settings-1');
    // The success toast landing in the store also flushes the post-response
    // state update (ToastContainer is not mounted here).
    await vi.waitFor(() => {
      const toasts = useUIStore.getState().toasts;
      expect(toasts.some((t) => t.type === 'success')).toBe(true);
    });
  });

  it('confirm dismissed: no request, no marker', async () => {
    callCapabilityMock.mockResolvedValue({ value: 'old-ws' });
    const fetchMock = vi.fn();
    vi.stubGlobal('fetch', fetchMock);
    vi.spyOn(window, 'confirm').mockReturnValue(false);

    render(<WorkspaceBlock />);
    const input = await screen.findByLabelText('工作目录');
    fireEvent.change(input, { target: { value: 'next-ws' } });
    fireEvent.blur(input);

    // Let pending microtasks settle, then assert nothing fired.
    await Promise.resolve();
    expect(fetchMock).not.toHaveBeenCalled();
    expect(useChatStore.getState().workspaceSwitchMarker).toBeNull();
  });
});

beforeEach(() => {
  callCapabilityMock.mockReset();
  useChatStore.setState({ workspaceSwitchMarker: null });
  useUIStore.setState({ toasts: [] });
  vi.stubGlobal('crypto', { randomUUID: () => 'marker-settings-1' });
  vi.stubGlobal('fetch', vi.fn());
  vi.spyOn(window, 'confirm').mockReturnValue(true);
  initI18n();
});
