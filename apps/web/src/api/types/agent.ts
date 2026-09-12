/**
 * @file types/agent.ts
 * @description Agent domain types: identity, sessions, messages, questionnaires,
 * memory, user profile, and context-window stats.
 *
 * Also hosts the legacy v1 SSE event payloads. Split out of api/types.ts;
 * pages and hooks still import from the @/api/types barrel.
 */

// ---------- Agent / Memory ----------

export type AgentId =
  | 'orchestrator'
  | 'recon'
  | 'explainer'
  | 'organizer'
  | 'graph_guide'
  | 'hub'
  | 'scout'
  | 'mentor'
  | 'navigator'
  | 'curator'
  | 'scribe'
  | 'atlas'
  | 'lucien'
  | 'iris'
  | 'elio'
  | 'miyai';

export interface AgentSession {
  id: string;
  title: string;
  project_id?: string | null;
  project_ids?: string[];
  agent: AgentId;
  created_ts: number;
  updated_ts: number;
  source?: 'chat' | 'analyze' | 'import' | 'graph';
  status?: 'active' | 'archived';
  /** Unread marker for the session list UI (legacy multi-session support is archived). */
  unread?: boolean;
  /** Update time in ISO form (legacy multi-session support is archived). */
  updated_at?: string;
}

export interface AgentSessionDetail extends AgentSession {
  messages: AgentMessage[];
}

export interface AgentProfile {
  id: string;
  key: AgentId;
  name?: string;
  display_name: string;
  style: string;
  system_prompt: string;
  default_mode: string;
  tool_allow: string[] | null;
  description?: string;
  avatar?: string;
  catchphrases?: string[];
}

export interface AgentMessage {
  id: string;
  session_id: string;
  agent: AgentId;
  role: 'user' | 'assistant' | 'tool' | 'system';
  content?: string;
  thinking?: string;
  tool_call?: ToolCallData;
  tool_calls?: ToolCallData[];
  subagents?: Array<{
    agentId: AgentId;
    task?: string;
    reason?: string;
    status: 'running' | 'ok' | 'question' | 'error';
    thinking?: string;
    output?: string;
  }>;
  question?: AgentQuestion;
  question_answer?: QuestionAnswerRecord;
  agent_switch?: { from: string; to: string; reason?: string };
  created_at: string;
  created_ts?: number;
}

export interface ToolCallData {
  name: string;
  args: Record<string, unknown>;
  result?: unknown;
  ts?: number;
  status?: 'running' | 'ok' | 'error';
}

export type QuestionItem =
  RadioQuestion | CheckboxQuestion | SliderQuestion | DragSortQuestion | KnowledgeMapQuestion;

export interface AgentQuestion {
  question_id: string;
  intro: { type: 'markdown'; content: string };
  questions: QuestionItem[];
  actions: {
    submit: { text: string; style: 'primary' | 'secondary' | 'ghost' | 'danger' | 'link' };
    skip?: { text: string; style: 'ghost' };
  };
  allow_skip: boolean;
  timeout: number | null;
}

export interface RadioQuestion {
  id: string;
  text: string;
  type: 'radio';
  options: RadioOption[];
  allow_other?: boolean;
  exam?: boolean;
}

export interface RadioOption {
  value: string;
  label: string;
  description?: string;
}

export interface CheckboxQuestion {
  id: string;
  text: string;
  type: 'checkbox';
  options: CheckboxOption[];
}

export interface CheckboxOption {
  value: string;
  text: string;
}

export interface SliderQuestion {
  id: string;
  text: string;
  type: 'slider';
  min: number;
  max: number;
  labels?: Record<string, string>;
}

export interface DragSortQuestion {
  id: string;
  text: string;
  type: 'drag_sort';
  items: string[];
}

export interface KnowledgeMapQuestion {
  id: string;
  text: string;
  type: 'knowledge_map';
  tree: KnowledgeNode[];
}

export interface KnowledgeNode {
  id: string;
  label: string;
  children?: KnowledgeNode[];
}

export type QuestionAnswer =
  | { type: 'radio'; value: string; other_text?: string; question_id?: string }
  | { type: 'checkbox'; values: string[]; question_id?: string }
  | { type: 'slider'; value: number; question_id?: string }
  | { type: 'drag_sort'; order: string[]; question_id?: string }
  | { type: 'knowledge_map'; checked: string[]; question_id?: string };

export interface QuestionAnswerRecord {
  question: AgentQuestion;
  answers: QuestionAnswer[];
  skipped?: boolean;
  summary: string;
  details: { question: string; answer: string }[];
}

export interface AgentPermissions {
  global: { can_write: boolean; can_delete: boolean; can_publish: boolean };
  per_capability: Record<string, { can_call: boolean }>;
}

export interface MemoryItem {
  id: string;
  content: string;
  /** Runtime category set: exactly these 4 values. */
  category: 'summary' | 'goal' | 'tech' | 'preference';
  created_ts?: number;
  /** ISO form (constructed locally by the client). */
  created_at?: string;
  source?: 'user' | 'inferred' | 'agent';
  confidence?: number;
}

export interface MemoryProposal {
  id: string;
  /** Consumed by the pending-memory card via value/agent_id/kind. */
  value: string;
  agent_id?: string;
  kind?: string;
}

export interface UserProfile {
  identity: LearnerIdentity;
  goals: Goal[];
  tech_proficiency: TechProficiencyEntry[];
  learning_style: string;
  verbosity: 'concise' | 'normal' | 'detailed';
  preferences: LearningPreferences;
  memory_items?: MemoryItem[];
  pending_memory_proposals?: MemoryProposal[];
}

export interface LearnerIdentity {
  background: string;
  current_role: string;
  experience_years: number;
  languages: string[];
}

export interface Goal {
  id?: string;
  title?: string;
  text?: string;
  priority?: number;
  status: 'active' | 'completed' | 'paused';
  progress?: number;
}

export interface TechProficiencyEntry {
  tech: string;
  level: 'novice' | 'intermediate' | 'advanced' | 'expert';
  source: 'self' | 'inferred' | 'verified';
}

export interface LearningPreferences {
  preferred_formats: string[];
  avoid_topics: string[];
  pace: 'slow' | 'normal' | 'fast';
}

export interface ContextWindowSegment {
  label: string;
  tokens: number;
  type?: 'system' | 'history' | 'tools' | 'memory' | 'output';
}

export interface ContextWindowStats {
  total: number;
  total_tokens: number;
  context_limit: number;
  max: number;
  segments: ContextWindowSegment[];
  model: string;
  input_tokens: number;
  output_tokens: number;
}

// ---------- SSE events (legacy v1 shapes) ----------

/** SSE event envelope. */
export interface SSEEvent {
  event: string;
  data: Record<string, unknown>;
}

export type SSEEventType =
  | 'text_delta'
  | 'thinking'
  | 'tool_call'
  | 'tool_result'
  | 'question'
  | 'agent_switch'
  | 'subagent_start'
  | 'subagent_thinking'
  | 'subagent_text'
  | 'subagent_done'
  | 'select_repos'
  | 'session_projects'
  | 'done'
  | 'error';

export interface SSETextDelta {
  type: 'text_delta';
  /** Runtime field name is content (consumed by sseHandlers, ProjectDetailPage,
   *  useTrendingSpotlight, formerly useTrendingScoutSpot). */
  content: string;
}

export interface SSEThinking {
  type: 'thinking';
  /** Runtime field name is content. */
  content: string;
}

export interface SSEToolCall {
  type: 'tool_call';
  name: string;
  args: Record<string, unknown>;
  call_id: string;
}

export interface SSEToolResult {
  type: 'tool_result';
  call_id: string;
  result: unknown;
  status: 'ok' | 'error';
}

export interface SSEAgentSwitch {
  type: 'agent_switch';
  from: string;
  to: string;
  reason?: string;
}

export interface SSESubagentStart {
  type: 'subagent_start';
  /** Runtime value is the snake_case agent_id (legacy multi-session agentStore archived). */
  agent_id: AgentId;
  task?: string;
  reason?: string;
}

export interface SSESubagentDone {
  type: 'subagent_done';
  /** Runtime value is the snake_case agent_id (legacy multi-session agentStore archived). */
  agent_id: AgentId;
  status: 'ok' | 'question' | 'error';
  thinking?: string;
  output?: string;
}

export interface SSEError {
  type: 'error';
  message: string;
  code?: string;
}

// SSE shapes are deprecated in the new frontend; legacy hooks may still consume
// them — the bridge layer translates.
