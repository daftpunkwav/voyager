/**
 * @file types
 * @description Type definitions shared across team-page sections.
 */

/** Running subagent instance (from list_subagents.running). */
export interface RunningSubagent {
  id: string;
  name: string;
  status: string;
  goal: string;
  started_ts: number;
  last_step?: string;
}

/** Resumable/abandonable checkpoint entry (from list_resumable_checkpoints.items).
 *  status is the on-disk state; it becomes paused after boot.
 *  resumable=false means an orphan entry (conversational or non-react run):
 *  only "abandon" is offered, no "resume". */
export interface ResumableCheckpoint {
  run_id: string;
  status: string;
  goal: string;
  instance_name: string;
  started_ts: number;
  last_step?: string;
  mode: string;
  /** false = orphan that can only be abandoned; true = task-type react run that can resume */
  resumable?: boolean;
  /** Marks conversational entries (used to identify orphans) */
  conversational?: boolean;
  /** true = ReAct crashed mid-turn; resume picks up from where it stopped, and the UI shows it as interrupted */
  in_turn?: boolean;
}

/** list_subagents.definitions entry; allowed_tools=null means no restriction (all tools);
 *  null round limits mean follow global, and an empty network tier inherits the global setting. */
export interface SubagentDef {
  name: string;
  mode: string;
  description: string;
  persona: string;
  allowed_tools: string[] | null;
  max_rounds?: number | null;
  max_tool_calls?: number | null;
  network_mode?: string;
}

/** Persona preset entry (from list_personas). */
export interface PersonaItem {
  key: string;
  display_name: string;
  style: string;
  default_mode: string;
  tool_allow: string[] | null;
  system_prompt: string;
}

/** Tool catalog entry (from list_tools). */
export interface ToolItem {
  name: string;
  description: string;
}
