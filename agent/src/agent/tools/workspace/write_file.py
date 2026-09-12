"""write_file tool: jailed whole-file write (parent directories created).

Writes are confined to the workspace roots and the additional read-write
roots; the L2 tier for user directories is judged by the policy layer.
"""

from __future__ import annotations

from agent.tools.core.base import AgentTool
from agent.tools.workspace.jail import Jail


def write_file_tool(jail: Jail) -> AgentTool:
    def write_file(path: str, content: str) -> dict:
        target = jail.resolve(path, allow_write_roots=True)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return {"written": str(target), "chars": len(content)}

    return AgentTool(
        name="write_file",
        description="在工作目录内写文件(自动建父目录)",
        handler=write_file,
        dimension="fs",
        write=True,
        schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
        },
    )


__all__ = ["write_file_tool"]
