/**
 * @file projectDetailSend
 * @description Phase-70 C unit tests: ProjectDetailPage.runAgent send
 * ordering (aligned with phase-68 C EmbedAgentChat). When the quota blocks
 * (the sendToChat port rejects): no optimistic user / "sent to main chat"
 * line is inserted, only an error toast; on success both the user and system
 * lines land. The page receives cross-domain actions via ProjectDetailPorts:
 * we pass port mocks directly instead of mocking chatSend/useNotes/useGraph
 * (the page itself no longer depends on them).
 */

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { initI18n } from '@/i18n';

const { project, sendUserTurnMock } = vi.hoisted(() => ({
  project: {
    id: 'proj1',
    name: 'octocat/hello-world',
    description: 'demo repo',
    stars: 42,
    language: 'TypeScript',
    imported_at: '2026-01-01T00:00:00Z',
    url: 'https://github.com/octocat/hello-world',
    progress: 'learning',
    tags: [],
    category_id: '',
    source: 'github',
  },
  sendUserTurnMock: vi.fn(),
}));

vi.mock('@/hooks/useProjects', () => ({
  useProject: () => ({ data: project, isLoading: false, isError: false }),
  useProjects: () => ({ data: { items: [] } }),
  useProjectReadme: () => ({
    data: null,
    isLoading: false,
    isFetching: false,
    isError: false,
    refetch: vi.fn(),
  }),
  useCategories: () => ({ data: [] }),
  useTags: () => ({ data: [] }),
  useUpdateProgress: () => ({ mutate: vi.fn() }),
  useDeleteProject: () => ({ mutate: vi.fn() }),
  // Needed by EditProjectModal (open=false but the hook is still called)
  useUpdateProject: () => ({ mutate: vi.fn(), isPending: false }),
  useSetProjectTags: () => ({ mutate: vi.fn(), isPending: false }),
  useCreateTag: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock('@/hooks/useCodeGraph', () => ({
  useIndexStatus: () => ({ data: null, isError: false }),
  useTriggerIndex: () => ({ mutate: vi.fn(), isPending: false }),
  useDeleteIndex: () => ({ mutate: vi.fn(), isPending: false }),
}));

import { ProjectDetailPage } from '@/pages/sources/ProjectDetailPage';
import { useUIStore } from '@/stores/uiStore';

beforeAll(() => {
  // Page copy moved to the sources ns: initialize explicitly (default zh-CN, assertions keep zh resource values)
  initI18n();
  // jsdom gap fallback (same as embedAgentChat.test)
  if (!window.matchMedia) {
    window.matchMedia = ((query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    })) as unknown as typeof window.matchMedia;
  }
  Element.prototype.scrollIntoView = () => {};
});

beforeEach(() => {
  sendUserTurnMock.mockReset();
  useUIStore.setState({ toasts: [] });
});

function renderPage() {
  const ports = {
    notes: [],
    related: [],
    openProjectNotes: vi.fn(),
    sendToChat: sendUserTurnMock,
  };
  return render(
    <MemoryRouter initialEntries={[`/sources/repo/${project.id}`]}>
      <Routes>
        <Route path="/sources/repo/:id" element={<ProjectDetailPage {...ports} />} />
      </Routes>
    </MemoryRouter>
  );
}

/** progress=learning → recon is recommended (Iris); the hero primary button is "Iris quick analysis" */
function clickRunAgent() {
  fireEvent.click(screen.getByRole('button', { name: 'Iris 快速分析' }));
}

describe('ProjectDetailPage.runAgent send ordering (phase-70 C)', () => {
  it('quota block: no optimistic line, no "sent to main chat" line, only an error toast', async () => {
    sendUserTurnMock.mockRejectedValue(new Error('daily token quota exhausted'));
    renderPage();
    clickRunAgent();

    await waitFor(() => expect(useUIStore.getState().toasts).toHaveLength(1));
    const toast = useUIStore.getState().toasts[0];
    expect(toast.type).toBe('error');
    expect(toast.message).toBe('daily token quota exhausted');

    expect(sendUserTurnMock).toHaveBeenCalledWith(
      expect.stringContaining('请以Iris分析仓库 octocat/hello-world')
    );
    // No err line and no "send success" false positive; stays on the AI analysis tab after switching
    expect(screen.queryByText('已发到主对话，请打开悬浮窗查看。')).not.toBeInTheDocument();
    expect(screen.queryByText(/发送失败：/)).not.toBeInTheDocument();
  });

  it('send success: lands the user line plus the "sent to main chat" system line', async () => {
    sendUserTurnMock.mockResolvedValue(undefined);
    renderPage();
    clickRunAgent();

    await waitFor(() => expect(screen.getByText('已发到主对话，请打开悬浮窗查看。')).toBeTruthy());
    expect(screen.getByText(`请以Iris分析仓库 ${project.name}（id=${project.id}）`)).toBeTruthy();
    expect(useUIStore.getState().toasts).toHaveLength(0);
  });
});
