"""glob tool: jailed filename listing by wildcard (* one level, ** recursive).

Read-only companion to list_dir; hits resolving outside the jail are dropped
(same laundering guard as grep).
"""

from __future__ import annotations

from typing import Any

from agent.tools.core.base import AgentTool
from agent.tools.workspace.jail import Jail

#: Cap on glob entries; beyond it the list is cut with the total kept.
_MAX_GLOB_ENTRIES = 200


def glob_tool(jail: Jail) -> AgentTool:
    def glob(pattern: str, path: str = ".") -> dict[str, Any] | str:
        if not (pattern or "").strip():
            return "[参数错误] pattern 不能为空"
        target = jail.resolve(path, allow_read_roots=True, allow_write_roots=True)
        if not target.is_dir():
            return f"[参数错误] path 不是目录: {jail.display(target)}"
        try:
            if "**" in pattern:
                hits = sorted(target.rglob(pattern))
            else:
                hits = sorted(target.glob(pattern))
        except (ValueError, NotImplementedError) as exc:
            return f"[参数错误] pattern 无效: {exc}"
        # Same laundering guard as grep: drop hits resolving outside.
        hits = [p for p in hits if jail.contains(p.resolve())]
        entries = [jail.display(p) + ("/" if p.is_dir() else "") for p in hits]
        truncated = len(entries) > _MAX_GLOB_ENTRIES
        return {
            "path": jail.display(target),
            "pattern": pattern,
            "files": entries[:_MAX_GLOB_ENTRIES],
            "total": len(entries),
            "truncated": truncated,
        }

    return AgentTool(
        name="glob",
        description="在工作目录内按通配符列文件(* 本层,** 递归)",
        handler=glob,
        dimension="fs",
        concurrent_safe=True,
        schema={
            "type": "object",
            "properties": {
                "pattern": {"type": "string"},
                "path": {"type": "string"},
            },
            "required": ["pattern"],
        },
    )


__all__ = ["glob_tool"]
