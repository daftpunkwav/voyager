/**
 * @file workspaceBrowser
 * @description Characterization of the workspace chooser: the directory
 * listing it renders and the navigation, pick and dismiss interactions it
 * owns. The picker API is stubbed, so the assertions pin the browser's own
 * behavior rather than the transport.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const { pickDirectoryMock } = vi.hoisted(() => ({ pickDirectoryMock: vi.fn() }));

vi.mock('@/api/workspace', () => ({
  pickDirectory: pickDirectoryMock,
  WORKDIR_KEY: 'agent.workspace.dir',
}));

import { WorkspaceBrowser } from '@/widgets/chat/workspace/WorkspaceBrowser';
import { initI18n } from '@/i18n';

const ROOT_LISTING = {
  path: '/',
  parent: null,
  home: '/home/tester',
  entries: [
    { name: 'projects', type: 'directory' },
    { name: 'readme.md', type: 'file' },
  ],
};

const NESTED_LISTING = {
  path: '/home/tester',
  parent: '/home',
  home: '/home/tester',
  entries: [{ name: 'notes', type: 'directory' }],
};

beforeAll(() => {
  initI18n();
});

beforeEach(() => {
  pickDirectoryMock.mockReset();
});

describe('WorkspaceBrowser', () => {
  it('lists the directories of the picked folder and leaves files out', async () => {
    pickDirectoryMock.mockResolvedValue(ROOT_LISTING);
    render(<WorkspaceBrowser onPick={vi.fn()} onClose={vi.fn()} />);

    expect(await screen.findByText('projects')).toBeTruthy();
    expect(screen.queryByText('readme.md')).toBeNull();
    expect(pickDirectoryMock).toHaveBeenCalledWith('');
  });

  it('shows the empty state for a folder without sub-directories', async () => {
    pickDirectoryMock.mockResolvedValue({ ...ROOT_LISTING, entries: [] });
    render(<WorkspaceBrowser onPick={vi.fn()} onClose={vi.fn()} />);

    expect(await screen.findByText('(无子目录)')).toBeTruthy();
  });

  it('navigates into a listed directory and shows its listing', async () => {
    pickDirectoryMock.mockResolvedValueOnce(ROOT_LISTING).mockResolvedValueOnce({
      path: '/projects',
      parent: '/',
      home: '/home/tester',
      entries: [{ name: 'inner', type: 'directory' }],
    });
    render(<WorkspaceBrowser onPick={vi.fn()} onClose={vi.fn()} />);

    fireEvent.click(await screen.findByText('projects'));

    expect(await screen.findByText('inner')).toBeTruthy();
    expect(pickDirectoryMock).toHaveBeenLastCalledWith('/projects');
  });

  it('walks up to the parent folder and jumps to the home folder', async () => {
    pickDirectoryMock.mockResolvedValue(NESTED_LISTING);
    render(<WorkspaceBrowser onPick={vi.fn()} onClose={vi.fn()} />);

    fireEvent.click(await screen.findByText('上一级'));
    await waitFor(() => expect(pickDirectoryMock).toHaveBeenLastCalledWith('/home'));

    fireEvent.click(screen.getByText('主目录'));
    await waitFor(() => expect(pickDirectoryMock).toHaveBeenLastCalledWith('/home/tester'));
  });

  it('reports the trimmed path the user typed', async () => {
    const onPick = vi.fn();
    pickDirectoryMock.mockResolvedValue(ROOT_LISTING);
    render(<WorkspaceBrowser onPick={onPick} onClose={vi.fn()} />);
    await screen.findByText('projects');

    fireEvent.change(screen.getByLabelText('data/workspace'), {
      target: { value: '  /srv/data  ' },
    });
    fireEvent.click(screen.getByText('选择此目录'));

    expect(onPick).toHaveBeenCalledWith('/srv/data');
  });

  it('reports the dismissal without choosing a directory', async () => {
    const onClose = vi.fn();
    const onPick = vi.fn();
    pickDirectoryMock.mockResolvedValue(ROOT_LISTING);
    render(<WorkspaceBrowser onPick={onPick} onClose={onClose} />);
    await screen.findByText('projects');

    fireEvent.click(screen.getByText('取消'));

    expect(onClose).toHaveBeenCalled();
    expect(onPick).not.toHaveBeenCalled();
  });

  it('shows the failure message of a rejected listing', async () => {
    pickDirectoryMock.mockResolvedValue({
      ...ROOT_LISTING,
      error: { code: 'unreadable', message: '目录不可读' },
    });
    render(<WorkspaceBrowser onPick={vi.fn()} onClose={vi.fn()} />);

    expect(await screen.findByRole('alert')).toHaveTextContent('目录不可读');
  });
});
