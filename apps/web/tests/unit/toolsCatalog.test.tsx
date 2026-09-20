/**
 * @file toolsCatalog
 * @description Settings 工具 section unit tests: the roster renders grouped by
 * category (internal tools by dimension, bridge tools by domain prefix),
 * search and category chips filter it, write tools carry a badge, and
 * expanding a row lazily fetches describe_tool and renders the parameter
 * schema.
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';

const { callCapabilityMock } = vi.hoisted(() => ({ callCapabilityMock: vi.fn() }));

vi.mock('@/bridge/client', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/bridge/client')>()),
  callCapability: callCapabilityMock,
}));

import { ToolsCatalog } from '@/components/settings/tools/ToolsCatalog';
import { initI18n } from '@/i18n';

const TOOLS = [
  { name: 'read_file', description: 'read a file', dimension: 'fs', write: false },
  {
    name: 'write_file',
    description: 'write a file',
    dimension: 'fs',
    write: true,
  },
  { name: 'run_shell', description: 'run a shell command', dimension: 'shell', write: true },
  {
    name: 'notes__create_note',
    description: 'create a note',
    dimension: 'app',
    write: true,
  },
];

const READ_FILE_DETAIL = {
  name: 'read_file',
  description: 'read a file',
  dimension: 'fs',
  write: false,
  parameters: {
    type: 'object',
    properties: {
      path: { type: 'string', description: 'relative path' },
      offset: { type: 'integer' },
    },
    required: ['path'],
  },
};

beforeAll(() => {
  initI18n();
});

beforeEach(() => {
  callCapabilityMock.mockReset();
  callCapabilityMock.mockImplementation(
    (_domain: string, name: string, args: Record<string, unknown>) => {
      if (name === 'tools' && args?.action === 'list') return Promise.resolve(TOOLS);
      if (name === 'tools' && args?.action === 'describe') {
        return args.name === 'read_file'
          ? Promise.resolve(READ_FILE_DETAIL)
          : Promise.reject(new Error('unknown tool'));
      }
      return Promise.resolve({});
    }
  );
});

describe('settings tools catalog', () => {
  it('renders the roster grouped by category with counts and write badges', async () => {
    render(<ToolsCatalog />);
    await waitFor(() => expect(screen.getByText('read_file')).toBeTruthy());
    // Group headers: internal tools by dimension, bridge tools by domain prefix
    // (each label appears in its header and in the filter chip, hence getAllByText)
    expect(screen.getAllByText('文件').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('命令').length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText('笔记').length).toBeGreaterThanOrEqual(1);
    // Write badge on write-class tools, absent on read-only ones
    expect(screen.getAllByText('可写').length).toBe(3);
    // Total count in the toolbar
    expect(screen.getByText('4')).toBeTruthy();
  });

  it('search filters across names and descriptions', async () => {
    render(<ToolsCatalog />);
    await waitFor(() => expect(screen.getByText('read_file')).toBeTruthy());
    fireEvent.change(screen.getByLabelText('搜索工具…'), { target: { value: 'note' } });
    await waitFor(() => expect(screen.queryByText('read_file')).toBeNull());
    expect(screen.getByText('notes__create_note')).toBeTruthy();
  });

  it('category chips filter the roster to one group', async () => {
    render(<ToolsCatalog />);
    await waitFor(() => expect(screen.getByText('run_shell')).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: '文件 2' }));
    await waitFor(() => expect(screen.queryByText('run_shell')).toBeNull());
    expect(screen.getByText('write_file')).toBeTruthy();
    // The "all" chip restores the full roster
    fireEvent.click(screen.getByRole('button', { name: '全部' }));
    await waitFor(() => expect(screen.getByText('run_shell')).toBeTruthy());
  });

  it('expanding a row lazily calls tools(describe) and renders the parameter schema', async () => {
    render(<ToolsCatalog />);
    await waitFor(() => expect(screen.getByText('read_file')).toBeTruthy());
    fireEvent.click(screen.getByRole('button', { name: /read_file/ }));
    await waitFor(() =>
      expect(callCapabilityMock).toHaveBeenCalledWith('agent', 'tools', {
        action: 'describe',
        name: 'read_file',
      })
    );
    await waitFor(() => expect(screen.getByText('path')).toBeTruthy());
    expect(screen.getByText('relative path')).toBeTruthy();
    expect(screen.getByText('必填')).toBeTruthy();
    expect(screen.getByText('offset')).toBeTruthy();
    // Parameters render once per expanded row only
    expect(screen.getAllByText('参数').length).toBe(1);
  });
});
