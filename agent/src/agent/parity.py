"""Human/agent parity declaration: the frozen exception lists.

Every capability a human can call through REST is meant to be callable by
the agent as a tool with the same name (domains via the host bridge as
<domain>__<name>, the agent's own capabilities via tools/<group>/<name>.py).
Deviations from that rule are enumerated here — nowhere else — each with the
reason the asymmetry exists. The host parity test (test_parity_surface)
reads these tables; adding an entry is a deliberate, reviewed change.
"""

from __future__ import annotations

#: Agent-registry capabilities with no agent tool of the same name.
HUMAN_ONLY_CAPABILITIES: dict[str, str] = {
    # Interaction contract: moving the conversation the user is looking at
    # breaks the conversational contract; the agent navigates instead.
    "set_active_session": "moves the user's view (interaction integrity); agent uses navigate",
    # Direction human -> agent: the agent asks via ask_user and receives the
    # answer through the same broker; the reply channel is not a tool.
    "answer_question": "reply channel for AskUser (human -> agent direction)",
    "report_page_context": "UI -> agent page feed (human -> agent direction)",
    # Persisted session snapshot detail: the agent reads history through
    # read_history (paged, bounded) instead of dumping a whole snapshot.
    "get_session": "agent reads history via read_history (bounded paging)",
    # Already resident in the system prompt: a tool would be redundant.
    "list_skills": "skill index is resident in the system prompt",
    "list_personas": "persona roster is resident in the system prompt",
    # Privilege-escalation boundary: these write user_only settings
    # (agent.plugins.approved / approvals, agent.mcp.servers) that gate what
    # enters the agent's own tool surface; the settings layer rejects an
    # agent actor, so a tool would be a guaranteed refusal.
    "set_plugin_approval": "writes user_only setting agent.plugins.* (self-escalation boundary)",
    "add_mcp_server": "writes user_only setting agent.mcp.servers (self-escalation boundary)",
    "approve_mcp_tools": "writes user_only setting agent.mcp.servers (self-escalation boundary)",
    "remove_mcp_server": "writes user_only setting agent.mcp.servers (self-escalation boundary)",
    # The settings domain bridge (settings__get_settings / settings__set_setting)
    # already gives the agent the shared settings store; the agent registry's
    # pair is the human REST projection.
    "list_approvals": "approval memory widens the agent's own envelope; management is the user's prerogative",
    "revoke_approval": "approval memory widens the agent's own envelope; management is the user's prerogative",
    "get_settings": "reachable as settings__get_settings via the domain bridge",
    "set_setting": "reachable as settings__set_setting via the domain bridge",
    # The review gate decides when the agent may act: the switch must stay in
    # human hands (the agent can only submit a plan and wait).
    "plan_mode_set": "toggles the plan review gate; human-controlled by design",
    "goal_manage": "creates/pauses/resumes durable goals; the auto-continuation budget stays human-controlled",
}

#: Agent tools with no human capability of the same name: the agent's hands
#: and internal channels, or bounded readers of transports the human already
#: has a page for.
AGENT_ONLY_TOOLS: dict[str, str] = {
    "spawn_subagent": "agent's dispatch hand (human dispatches through chat)",
    "request_context": "subagent -> master internal channel",
    "activate_tools": "graded schema activation, per-instance mechanism",
    "read_board": "task-scoped shared notes among sibling subagents (no human board page)",
    "write_board": "task-scoped shared notes among sibling subagents (no human board page)",
    "read_events": "bounded reader of the activity feed (human has the activity page)",
    "read_history": "bounded reader of chat history (human has the chat page)",
    "read_file": "workspace hand",
    "write_file": "workspace hand",
    "edit_file": "workspace hand",
    "list_dir": "workspace hand",
    "delete_file": "workspace hand",
    "undo_writes": "workspace hand (rollback of the agent's own writes)",
    "grep": "workspace hand",
    "glob": "workspace hand",
    "run_shell": "workspace hand",
    "run_snippet": "workspace hand (in-harness lightweight snippet execution for teaching and scratchpads)",
    "todo_write": "plan hand (human reads via todo_read)",
    "web_fetch": "network hand",
    "web_search": "network hand",
    "ask_user": "agent -> human question channel",
    "reach_out": "one-shot proactive message (fire-and-forget; the human is the recipient)",
    "exit_plan_mode": "plan review submission (human approves through the ask channel)",
    "session_search": "bounded FTS reader of conversation history (human has the chat page)",
    "session_trace": "fork lineage reader (lineage is recorded for search, not a page)",
    "goal_read": "durable-goal status reader",
    "goal_write": "agent progress report (done/blocked only; lifecycle stays human-side)",
    "scratchpad": "in-harness working scratchpad for intermediate thinking and step tracking",
    "propose_skill": "proposes user skills from conversational experience, confirmed by human",
}

#: Transport-layer human surfaces that are not business capabilities and
#: therefore outside parity (R5): uploads (multipart), chat SSE, session
#: bootstrap. Listed for completeness; nothing to test.
TRANSPORT_ONLY: tuple[str, ...] = ("uploads", "chat.stream", "session.bootstrap")

__all__ = ["AGENT_ONLY_TOOLS", "HUMAN_ONLY_CAPABILITIES", "TRANSPORT_ONLY"]
