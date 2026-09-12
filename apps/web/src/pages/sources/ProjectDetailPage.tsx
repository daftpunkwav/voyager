/**
 * @file ProjectDetailPage
 * @description Project detail coordinator page (the sole page-as-module assembly point).
 *
 * Keeps only data-hook orchestration, event coordination, and layout assembly;
 * business sub-components live in this directory (ProjectHero / ProjectProgressCard /
 * ProjectReadmePanel / ProjectNotesCard / ProjectRelatedPanel / ProjectInfoCard /
 * ProjectAgentsCard / ProjectCodeGraphCard). The three cross-domain lines
 * (notes / graph / chat) are injected via ProjectDetailPorts by App; the page
 * only consumes sources data (useProject / useProjects / useCategories / useTags).
 *
 * Responsibilities:
 * - Orchestrate project data hooks: detail, readme, categories, tags,
 *   progress update, and delete confirmation
 * - Coordinate the four tabs (readme / notes / ai / related) and the
 *   sidebar cards, raising navigation and agent invocation
 * - Consume the injected cross-domain ports instead of importing notes,
 *   graph, or chat modules directly
 * - Feed the detail id/title to the page-awareness provider
 */
import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { i18n } from '@/i18n';
import {
  useCategories,
  useDeleteProject,
  useProject,
  useProjectReadme,
  useProjects,
  useTags,
  useUpdateProgress,
} from '@/hooks/useProjects';
import { EditProjectModal } from '@/components/project/EditProjectModal';
import { useUIStore } from '@/stores/uiStore';
import type { AgentId, Note } from '@/api/types';
import { LoadingSpinner } from '@/components/common/LoadingSpinner';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { splitRepoName } from '@/utils/format';
import { AGENT_CATALOG } from '@/constants/agentCatalog';
import { routes } from '@/utils/routes';
import { rememberSourceDetail } from './provider';
import { ProjectAiPanel, type ProjectAiLine } from '@/components/project/ProjectAiPanel';
import { CodeGraphIndexCard } from './ProjectCodeGraphCard';
import { ProjectHero } from './ProjectHero';
import { ProjectProgressCard } from './ProjectProgressCard';
import { ProjectReadmePanel } from './ProjectReadmePanel';
import { ProjectNotesCard } from './ProjectNotesCard';
import { ProjectRelatedPanel } from './ProjectRelatedPanel';
import { ProjectInfoCard } from './ProjectInfoCard';
import { ProjectAgentsCard } from './ProjectAgentsCard';

/** Expert personas for the detail sidebar (coordinator entry excluded) */
const DETAIL_AGENTS = AGENT_CATALOG.filter((a) => a.id !== 'orchestrator');

/** Cross-domain ports of the detail page: the notes / graph / chat lines are
 *  injected by the assembly layer (App). The page does not import notes/graph
 *  hooks or chatSend; removing a domain only requires changing the port's
 *  default/placeholder implementation in the assembly layer, not this page. */
export interface ProjectDetailPorts {
  /** Note list for this project (notes domain) */
  notes: Note[];
  /** L0 related projects (sorted by similarity, top 5) (graph domain) */
  related: { id: string; sim: number }[];
  /** Opens the notes page filtered by project (notes domain action) */
  openProjectNotes(projectId: string): void;
  /** Sends an analysis request to the main chat timeline (chat domain action) */
  sendToChat(text: string): Promise<void>;
}

function welcomeAiLine(projectName: string): ProjectAiLine {
  // Module-level (called from useState initializers / effects): uses the global
  // i18n instance instead of the useTranslation hook.
  return {
    id: 'welcome',
    role: 'assistant',
    content: i18n.t('sources:detail.welcome', { name: projectName }),
  };
}

type DetailTab = 'readme' | 'notes' | 'ai' | 'related';

export function ProjectDetailPage({
  notes,
  related,
  openProjectNotes,
  sendToChat,
}: ProjectDetailPorts) {
  const { t } = useTranslation('sources');
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const addToast = useUIStore((s) => s.addToast);
  const { data: project, isLoading, isError } = useProject(id);
  const { data: allProjects } = useProjects();
  const { data: categories = [] } = useCategories();
  const { data: tags = [] } = useTags();
  const updateProgress = useUpdateProgress();
  const deleteProject = useDeleteProject();

  // Feed the detail id / title to the page-awareness provider; the title is an empty string until it arrives (probe falls back to id)
  useEffect(() => {
    if (!id) {
      rememberSourceDetail(null);
      return;
    }
    rememberSourceDetail({ kind: 'repo', id, title: project?.name ?? '' });
  }, [id, project?.name]);

  const [tab, setTab] = useState<DetailTab>('readme');
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [editOpen, setEditOpen] = useState(false);
  const [activeAgent, setActiveAgent] = useState<AgentId>('recon');
  const [aiLines, setAiLines] = useState<ProjectAiLine[]>(() => [
    welcomeAiLine(t('sources:detail.welcomePlaceholderName')),
  ]);
  // README font size stays on the coordinator page so tab switches do not reset it
  const [fontSize, setFontSize] = useState(14);
  const [noteGenerating, setNoteGenerating] = useState(false);

  const {
    data: readmeData,
    isLoading: readmeLoading,
    isFetching: readmeFetching,
    isError: readmeError,
    refetch: refetchReadme,
  } = useProjectReadme(id, tab === 'readme' && Boolean(id));

  useEffect(() => {
    if (isError) {
      addToast({ type: 'error', message: t('sources:detail.projectMissing') });
      navigate(routes.sources, { replace: true });
    }
  }, [isError, navigate, addToast, t]);

  // Reset the message stream when switching projects
  useEffect(() => {
    if (!id) return;
    setAiLines([welcomeAiLine(t('sources:detail.welcomePlaceholderName'))]);
  }, [id, t]);

  // Refresh the welcome line once the project name is ready (only while no conversation has started)
  useEffect(() => {
    if (!project?.name) return;
    setAiLines((prev) => {
      if (prev.length === 1 && prev[0]?.id === 'welcome') {
        return [welcomeAiLine(project.name)];
      }
      return prev;
    });
  }, [project?.name]);

  const projectMap = useMemo(() => {
    const m = new Map<string, { name: string }>();
    for (const p of allProjects?.items ?? []) {
      m.set(p.id, { name: p.name });
    }
    return m;
  }, [allProjects]);

  const recommendedAgent: AgentId = project?.progress === 'mastered' ? 'explainer' : 'recon';
  const { repo } = splitRepoName(project?.name ?? '');
  const scribeName = repo || project?.name || '';

  /** Invokes the given expert agent to analyze the current project; the request goes to the main timeline, not a local fake stream. */
  const runAgent = async (agent: AgentId) => {
    if (!id) return;
    const resolved = (
      agent === 'orchestrator' || agent === 'hub' || agent === 'lucien' ? 'recon' : agent
    ) as AgentId;
    const meta = DETAIL_AGENTS.find((a) => a.id === resolved) ?? DETAIL_AGENTS[0];
    const agentName = meta?.name ?? 'Agent';
    const projectLabel = project?.name ?? id;
    const analyzeText = t('sources:detail.analyzeRequest', {
      agent: agentName,
      project: projectLabel,
      id,
    });
    setActiveAgent(resolved);
    setTab('ai');
    try {
      // Commit to the local view only after the send succeeds (aligned with EmbedAgentChat):
      // a quota-block error must not insert false-positive user / system lines
      await sendToChat(analyzeText);
      setAiLines((prev) => [
        ...prev,
        {
          id: `u_${Date.now()}`,
          role: 'user',
          content: analyzeText,
        },
        {
          id: `sys_${Date.now()}`,
          role: 'assistant',
          content: t('sources:detail.sentToChat'),
        },
      ]);
    } catch (err) {
      const message = err instanceof Error ? err.message : t('sources:detail.sendFailed');
      addToast({ type: 'error', message });
    }
  };

  const handleNewNote = () => {
    if (!id) return;
    openProjectNotes(id);
  };

  const readmeText = readmeData?.content || project?.readme || '';

  const copyReadme = async () => {
    if (!readmeText) return;
    try {
      await navigator.clipboard.writeText(readmeText);
      addToast({ type: 'success', message: t('sources:detail.readmeCopied') });
    } catch {
      addToast({ type: 'error', message: t('sources:detail.copyFailed') });
    }
  };

  const handleGenerateNote = async () => {
    if (!project) return;
    setNoteGenerating(true);
    try {
      await sendToChat(t('sources:detail.noteRequest', { project: project.name, id: project.id }));
      setAiLines((prev) => [
        ...prev,
        { id: `sys_${Date.now()}`, role: 'assistant', content: t('sources:detail.noteSent') },
      ]);
      setTab('ai');
    } catch (err) {
      const message = err instanceof Error ? err.message : t('sources:detail.noteFailed');
      addToast({ type: 'error', message });
    } finally {
      setNoteGenerating(false);
    }
  };

  if (isError) return null;
  if (isLoading || !project) return <LoadingSpinner />;

  return (
    <div className="pd-shell">
      <section className="pd-main">
        <ProjectHero
          project={project}
          recommendedAgent={recommendedAgent}
          noteGenerating={noteGenerating}
          onRunAgent={runAgent}
        />

        <ProjectProgressCard
          project={project}
          scribeName={scribeName}
          noteGenerating={noteGenerating}
          onProgressChange={(progress) => updateProgress.mutate({ id: project.id, progress })}
          onGenerateNote={handleGenerateNote}
        />

        <div className="pd-tabs" role="tablist">
          {(
            [
              ['readme', t('sources:detail.tab.readme'), notes.length, false],
              ['notes', t('sources:detail.tab.notes'), notes.length, true],
              ['ai', t('sources:detail.tab.ai'), 0, false],
              ['related', t('sources:detail.tab.related'), related.length, true],
            ] as const
          ).map(([key, label, count, showCount]) => (
            <button
              key={key}
              type="button"
              className="pd-tab"
              role="tab"
              aria-selected={tab === key ? 'true' : 'false'}
              data-testid={key === 'notes' ? 'tab-notes' : undefined}
              onClick={() => setTab(key)}
            >
              {label}
              {showCount && <span className="pd-tab-count">{count}</span>}
            </button>
          ))}
        </div>

        {tab === 'readme' && (
          <ProjectReadmePanel
            readmeText={readmeText}
            readmeLoading={readmeLoading}
            readmeFetching={readmeFetching}
            readmeError={readmeError}
            readmeMessage={readmeData?.message}
            fontSize={fontSize}
            onFontSizeChange={setFontSize}
            onRefresh={refetchReadme}
            onCopy={copyReadme}
          />
        )}

        {tab === 'notes' && (
          <ProjectNotesCard notes={notes} projectId={id} onNewNote={handleNewNote} />
        )}

        {tab === 'ai' && (
          <ProjectAiPanel
            projectName={project.name}
            agents={DETAIL_AGENTS}
            activeAgent={activeAgent}
            lines={aiLines}
            streaming={false}
            streamContent=""
            streamThinking=""
            onSelectAgent={(agentId) => setActiveAgent(agentId)}
            onRun={() => void runAgent(activeAgent)}
            onAbort={() => {}}
          />
        )}

        {tab === 'related' && <ProjectRelatedPanel related={related} projectMap={projectMap} />}
      </section>

      <aside className="pd-side">
        <ProjectInfoCard
          project={project}
          categories={categories}
          tags={tags}
          onEdit={() => setEditOpen(true)}
          onDelete={() => setDeleteOpen(true)}
        />

        <ProjectAgentsCard
          agents={DETAIL_AGENTS}
          recommendedAgent={recommendedAgent}
          activeAgent={activeAgent}
          active={tab === 'ai'}
          noteGenerating={noteGenerating}
          onRunAgent={runAgent}
        />

        {id ? <CodeGraphIndexCard projectId={id} /> : null}
      </aside>

      <EditProjectModal
        open={editOpen}
        project={project}
        categories={categories}
        tags={tags}
        onClose={() => setEditOpen(false)}
      />

      <ConfirmDialog
        open={deleteOpen}
        title={t('sources:detail.deleteTitle')}
        message={t('sources:detail.deleteConfirm', { name: project.name })}
        danger
        onConfirm={() => {
          deleteProject.mutate(project.id, { onSuccess: () => navigate(routes.sources) });
          setDeleteOpen(false);
        }}
        onCancel={() => setDeleteOpen(false)}
      />
    </div>
  );
}
