"""Human/agent parity declaration: the frozen exception lists.

Every capability a human can call through REST is meant to be callable by
the agent as a tool with the same name (domains via the host bridge as
<domain>__<name>, the agent's own capabilities via the aggregated tools).
Deviations from that rule are enumerated here — nowhere else — each with the
reason the asymmetry exists. The host parity test (test_parity_surface)
reads these tables; adding an entry is a deliberate, reviewed change.

The exceptions classify into four kinds (design §5): directional channels
(interaction direction, not privilege), agent runtime mechanisms,
interaction/lifecycle invariants (enforced at dispatch or by the settings
framework's user_only rejection, not by this table), and the agent's hands
(tools without a human REST mirror).
"""

from __future__ import annotations

#: Agent-registry capabilities with no agent tool of the same name.
HUMAN_ONLY_CAPABILITIES: dict[str, str] = {
    # Direction human -> agent: the agent asks via ask_user and receives the
    # answer through the same broker; the reply channel is not a tool.
    "answer_question": "reply channel for AskUser (human -> agent direction)",
    "report_page_context": "UI -> agent page feed (human -> agent direction)",
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
    "get_settings": "reachable as settings__get_settings via the domain bridge",
    "set_setting": "reachable as settings__set_setting via the domain bridge",
    # The review gate decides when the agent may act: the switch must stay in
    # human hands (the agent can only submit a plan and wait).
    # Turn rating shapes the user's own view of the conversation.
    "rate_turn": "the user rates the agent's turn, never the other way around",
}

#: Agent tools with no human capability of the same name: the agent's hands
#: and internal channels, or bounded readers of transports the human already
#: has a page for.
AGENT_ONLY_TOOLS: dict[str, str] = {
    "request_context": "subagent -> master internal channel",
    "activate_tools": "graded schema activation, per-instance mechanism",
    "read": "workspace hand",
    "write": "workspace hand",
    "edit": "workspace hand",
    "grep": "workspace hand",
    "glob": "workspace hand",
    "bash": "workspace hand",
    "web_fetch": "network hand",
    "web_search": "network hand",
    "ask_user": "agent -> human question channel",
    "scratchpad": "in-harness working scratchpad for intermediate thinking and step tracking",
}

#: Transport-layer human surfaces that are not business capabilities and
#: therefore outside parity (R5): uploads (multipart), chat SSE, session
#: bootstrap. Listed for completeness; nothing to test.
TRANSPORT_ONLY: tuple[str, ...] = ("uploads", "chat.stream", "session.bootstrap")

__all__ = ["AGENT_ONLY_TOOLS", "HUMAN_ONLY_CAPABILITIES", "TRANSPORT_ONLY"]
