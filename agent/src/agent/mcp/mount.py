"""External MCP tool mounting: turn remote tools into AgentTools in the
root Toolbelt.

Connection is pool.py's job; mount.py only handles how tool names are derived,
how the AgentTool is built, and register-after-approval / unregister-on-removal.
Approval is only the gate into the registry; calls still go through the
capability app whitelist dimension (dimension="app", target = tool name, the
same agent.app.allowed/denied set as bridge tools).
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from agent.mcp.session import CALL_TIMEOUT, McpSession
from agent.tools.core.base import AgentTool, Toolbelt


def _tool_name(sid: str, remote_name: str) -> str:
    """Remote tool name -> local tool-surface name: mcp__<id>__<safe>."""
    safe = re.sub(r"[^A-Za-z0-9_]", "_", remote_name) or "tool"
    return f"mcp__{sid}__{safe}"


def _build_tool(cfg: dict, session: McpSession, remote: dict) -> AgentTool:
    """Build an AgentTool for one remote tool; remote failures come back as
    text results for the LLM instead of breaking the tool loop."""
    remote_name = str(remote.get("name") or "")
    tool_name = _tool_name(cfg["id"], remote_name)

    async def handler(**kwargs: Any) -> str:
        try:
            return await asyncio.wait_for(session.call_tool(remote_name, kwargs), CALL_TIMEOUT)
        except Exception as exc:  # noqa: BLE001
            return f"[MCP failed] {tool_name}: {exc}"

    schema = (
        remote.get("schema")
        or remote.get("inputSchema")
        or {
            "type": "object",
            "additionalProperties": True,
        }
    )
    return AgentTool(
        name=tool_name,
        # description carries the display name so the model can tell apart
        # same-named remote tools
        description=f"[MCP:{cfg['name']}] {remote.get('description') or remote_name}",
        handler=handler,
        schema=schema,
        # approval is only the registry gate; calls go through the app dimension
        # (target = tool name, same agent.app.allowed set)
        dimension="app",
    )


def unmount(toolbelt: Toolbelt | None, sid: str) -> list[str]:
    """Unmount mcp__<sid>__* from the root registry; returns the names actually
    removed."""
    if toolbelt is None:
        return []
    prefix = f"mcp__{sid}__"
    names = [n for n in toolbelt.names() if n.startswith(prefix)]
    toolbelt.unregister(names)
    return names


def _resource_tools(cfg: dict, session: McpSession) -> dict[str, AgentTool]:
    """Synthesize the resource access pair for one server: list + read,
    mounted only when the approval list covers them (same gate as tools:
    "*" or the explicit names - approval is never inferred)."""

    async def list_handler() -> str:
        list_res = getattr(session, "list_resources", None)
        if list_res is None:
            return f"[MCP failed] mcp__{cfg['id']}__list_resources: server has no resources"
        try:
            resources = await asyncio.wait_for(list_res(), CALL_TIMEOUT)
        except Exception as exc:  # noqa: BLE001
            return f"[MCP failed] mcp__{cfg['id']}__list_resources: {exc}"
        if not resources:
            return "no resources"
        lines = []
        for r in resources:
            line = f"{r.get('uri', '')}  {r.get('name', '')}"
            if r.get("description"):
                line += f"  {r['description']}"
            lines.append(line)
        return "\n".join(lines)

    async def read_handler(uri: str) -> str:
        read_res = getattr(session, "read_resource", None)
        if read_res is None:
            return f"[MCP failed] mcp__{cfg['id']}__read_resource({uri}): server has no resources"
        try:
            return await asyncio.wait_for(read_res(uri), CALL_TIMEOUT)
        except Exception as exc:  # noqa: BLE001
            return f"[MCP failed] mcp__{cfg['id']}__read_resource({uri}): {exc}"

    prefix = f"mcp__{cfg['id']}__"
    return {
        f"{prefix}list_resources": AgentTool(
            name=f"{prefix}list_resources",
            description=f"[MCP:{cfg['name']}] list resources exposed by this server",
            handler=list_handler,
            schema={"type": "object", "properties": {}},
            dimension="app",
        ),
        f"{prefix}read_resource": AgentTool(
            name=f"{prefix}read_resource",
            description=f"[MCP:{cfg['name']}] read one resource by uri (see list_resources)",
            handler=read_handler,
            schema={
                "type": "object",
                "properties": {"uri": {"type": "string"}},
                "required": ["uri"],
            },
            dimension="app",
        ),
    }


def remount(
    toolbelt: Toolbelt | None,
    cfg: dict,
    session: McpSession | None,
    remote_tools: list[dict],
    approved: list[str],
) -> list[str]:
    """Mount per the approved list (["*"] = everything from preview); the old
    mount is removed first so stale names cannot linger.

    Requires a preview to be present (call preview() first); returns the tool
    names mounted this time. When the session speaks resources, the
    list_resources/read_resource pair mounts under the same approval gate.
    """
    if toolbelt is None:
        return []
    # Unmount first: even with no session/preview this time, no stale names may
    # remain (same behavior as before the split)
    unmount(toolbelt, cfg["id"])
    if session is None:
        return []
    covers_resources = "*" in approved or "resources" in approved
    caps = getattr(session, "server_capabilities", {})
    if covers_resources and isinstance(caps, dict) and caps and "resources" not in caps:
        covers_resources = False  # real session says it has no resource capability
    if not remote_tools and not covers_resources:
        return []
    if approved == ["*"]:
        selected = list(remote_tools)
    else:
        want = set(approved)
        selected = [t for t in remote_tools if t.get("name") in want]
    tools = {
        _tool_name(cfg["id"], str(t.get("name") or "")): _build_tool(cfg, session, t)
        for t in selected
    }
    if covers_resources and callable(getattr(session, "list_resources", None)):
        tools.update(_resource_tools(cfg, session))
    if not tools:
        return []
    toolbelt.register(tools)
    return sorted(tools)
