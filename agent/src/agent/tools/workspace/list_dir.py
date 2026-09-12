"""list_dir tool: jailed directory listing (read sees all root kinds)."""

from __future__ import annotations

from agent.tools.core.base import AgentTool
from agent.tools.workspace.jail import Jail


def list_dir_tool(jail: Jail) -> AgentTool:
    def list_dir(path: str = ".") -> list[str] | str:
        target = jail.resolve(path, allow_read_roots=True, allow_write_roots=True)
        try:
            entries = list(target.iterdir())
        except FileNotFoundError:
            return f"[失败] 目录不存在: {jail.display(target)}"
        except NotADirectoryError:
            return f"[参数错误] path 不是目录: {jail.display(target)}"
        return sorted(p.name + ("/" if p.is_dir() else "") for p in entries)

    return AgentTool(
        name="list_dir",
        description="列出工作目录内某目录的内容",
        handler=list_dir,
        dimension="fs",
        concurrent_safe=True,
        schema={"type": "object", "properties": {"path": {"type": "string"}}},
    )


__all__ = ["list_dir_tool"]
