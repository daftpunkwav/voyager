/**
 * @file events.ts
 * @description Event type constants, aligned with the backend platform_contracts.DomainEvent.
 *
 * Publishers and subscribers must reference these constants instead of
 * scattering literals, so a backend rename cannot silently detach a consumer.
 * The wildcard subscription patterns (e.g. "task.*") are globs, not concrete
 * types, and stay literals at the subscribe sites.
 */

export const EventType = {
  /** User message sent to an agent (delivered via the gateway chat) */
  USER_MESSAGE: 'user.message',
  /** Presence heartbeat */
  USER_ONLINE: 'user.online',
  /** Page activity beacon */
  USER_ACTIVITY: 'user.activity',
  /** Task lifecycle (long-running task progress) */
  TASK_ENQUEUED: 'task.enqueued',
  TASK_PROGRESS: 'task.progress',
  TASK_COMPLETED: 'task.completed',
  TASK_FAILED: 'task.failed',
  /** Agent reply */
  AGENT_MESSAGE: 'agent.message',
  /** Agent needs user interaction (dialog/choice/confirmation) */
  AGENT_ASK: 'agent.ask',
  /** Tool/round step (timeline + inline trace) */
  AGENT_STEP: 'agent.step',
  /** Streaming text delta */
  AGENT_DELTA: 'agent.delta',
  /** Agent observation notice (resource ready etc.; acted = auto-dispatched) */
  AGENT_OBSERVE: 'agent.observe',
  /** L1 permission notice (info toast only, never the timeline) */
  AGENT_POLICY_NOTIFY: 'agent.policy.notify',
  /** Agent asks the frontend to navigate */
  AGENT_NAVIGATE: 'agent.navigate',
  /** Agent detected a repeated tool flow and proposes saving it as a skill */
  SKILL_PROPOSED: 'skill.proposed',
  /** A chat session was deleted (session field = the deleting turn's session, when agent-driven) */
  SESSION_DELETED: 'session.deleted',
  /** Note lifecycle */
  NOTE_CREATED: 'note.created',
  NOTE_EDITED: 'note.edited',
  NOTE_DELETED: 'note.deleted',
  NOTE_RESTORED: 'note.restored',
  NOTE_PURGED: 'note.purged',
  NOTE_PURGED_BATCH: 'note.purged_batch',
  /** Notes UI settings changed (mode/layout/density...) */
  NOTES_UI_CHANGED: 'notes.ui.changed',
  /** Sources library lifecycle */
  SOURCE_ADDED: 'source.added',
  SOURCE_READY: 'source.ready',
  SOURCE_REMOVED: 'source.removed',
  /** A settings key changed (hot-reload) */
  SETTINGS_CHANGED: 'settings.changed',
  /** LLM provider fallback recorded */
  LLM_FALLBACK: 'llm.fallback',
  /** Graph C engine unreachable, Python engine took over */
  GRAPH_ENGINE_FALLBACK: 'graph.engine.fallback',
  /** Office document lifecycle (doc and slides modules share the vocabulary) */
  DOC_CREATED: 'doc.created',
  DOC_EDITED: 'doc.edited',
  DOC_DELETED: 'doc.deleted',
  /** Agent workspace hot-switched (cross-tab notice, not a timeline event) */
  WORKSPACE_SWITCHED: 'workspace.switched',
  /** Service health state transition (data source of the badge bar) */
  SERVICE_HEALTH_CHANGED: 'service.health.changed',
} as const;

export type EventTypeValue = (typeof EventType)[keyof typeof EventType];
