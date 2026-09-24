"""Dependency container for agent capabilities.

Kept as a single dataclass, injected by build.py on every
build_agent_registry call. Do not split it into individual fields and do
not introduce module-level global `_deps`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from agent.context.pages import PageContextRegistry
from agent.memory import Memory
from agent.skills.loader import SkillLoader
from agent.subagent.registry import SubagentRegistry
from agent.subagent.spawn import Spawner
from agent.tools.interact.question_broker import AskUser


@dataclass
class CapabilityDeps:
    settings: Any  # SettingsStore
    memory: Memory
    skills: SkillLoader
    spawner: Spawner
    subagents: SubagentRegistry
    pages: PageContextRegistry
    asker: AskUser
    toolbelt: Any  # Toolbelt (data source for list_tools)
    mcp: Any  # McpClientPool (external MCP; config writes go through actor for audit)
    meter: Any  # Meter (in-memory, per-resource; same instance as metered_llm)
    checkpoints: Any  # CheckpointStore (list of resumable checkpoints)
    plugins: Any  # PluginManager (plugin discovery and whole-package approval)
    user_hooks: Any  # UserHookReloader (hot reload of user workspace/hooks)
    todos: Any  # TodoStore (workspace/todo.json; plan panel + todo_read capability)
    sessions: Any  # SessionManager (chat sessions; human capabilities + agent tools share it)
    jobs: Any  # runtime.jobs_view.JobsView (task.* projection; read-only)
    job_cancel: Any  # async (job_id) -> dict, injected by the host (routes to the source domain)
    blackboard: Any  # master.blackboard.Blackboard (task-scoped shared notes)
    plan_gates: Any = None  # context.plan_gate.PlanGates (session review-phase state)
    goal_manager: Any = None  # master.goal.GoalManager (durable session goals)
    skills_dir: Any = None  # user skills directory (skill propose writes there)
    dispatch: Any = None  # master.dispatch_task (subagent spawn action)
    team_handoff: Any = None  # master.queue_member_turn (subagent handoff action)
    task_board: Any = None  # master.task_board.TaskBoard (teamboard capability)
    session_index: Any = None  # runtime.session_index.SessionIndex (session search action)
    log: Any = None  # platform_eventbus.EventLog (session read action pages the history)
    job_reorder: Any = None  # async (job_id, priority) -> dict, host-routed to the source domain
