"""Agent's own tools: Toolbelt wrapper and per-group tool factories.

Every tool is one file under tools/<group>/<name>.py exporting
`<name>_tool(...) -> AgentTool`; the group packages expose zero-logic
`*_tools` aggregators that this module re-exports for assembly and tests.
"""

from agent.tools.context import context_tools
from agent.tools.core.activate import CORE_TOOLS, domain_prefixes, graded_toolbelt
from agent.tools.core.base import AgentTool, ConfirmFn, NotifyFn, Toolbelt
from agent.tools.core.outcome import ToolResult
from agent.tools.core.registry import StaticToolSource, ToolRegistry
from agent.tools.extension import extension_tools
from agent.tools.interact import (
    AGENT_ASK,
    AskUser,
    Question,
    ask_user_tool,
    reach_out_tool,
    request_context_tool,
)
from agent.tools.jobs import jobs_tools
from agent.tools.memory import memory_tools
from agent.tools.net import web_tools
from agent.tools.observe import observe_tools
from agent.tools.plan import goal_tools, plan_tools, scratchpad_tool
from agent.tools.session import session_tools
from agent.tools.skill import skill_tools
from agent.tools.team import spawn_tool, team_tools
from agent.tools.tools import tools_tools
from agent.tools.workspace import (
    DEFAULT_CATEGORIES,
    TodoStore,
    ensure_workdir,
    fs_tools,
    search_tools,
    shell_tools,
    todo_tools,
)

__all__ = [
    "AGENT_ASK",
    "CORE_TOOLS",
    "DEFAULT_CATEGORIES",
    "AgentTool",
    "AskUser",
    "ConfirmFn",
    "NotifyFn",
    "Question",
    "StaticToolSource",
    "TodoStore",
    "ToolRegistry",
    "ToolResult",
    "Toolbelt",
    "ask_user_tool",
    "context_tools",
    "domain_prefixes",
    "ensure_workdir",
    "extension_tools",
    "fs_tools",
    "goal_tools",
    "graded_toolbelt",
    "jobs_tools",
    "memory_tools",
    "observe_tools",
    "plan_tools",
    "reach_out_tool",
    "request_context_tool",
    "scratchpad_tool",
    "search_tools",
    "session_tools",
    "shell_tools",
    "skill_tools",
    "spawn_tool",
    "team_tools",
    "todo_tools",
    "tools_tools",
    "web_tools",
]
