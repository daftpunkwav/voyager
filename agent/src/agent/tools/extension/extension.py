"""extension tool: plugins / external MCP / user hooks in one tool —
kind×action grid bound to the same extension capability (audit symmetry;
schema derived from the capability)."""

from __future__ import annotations

from platform_capability import Registry

from agent.tools.core.base import AgentTool
from agent.tools.core.self_capability import AuditSinks, capability_tool


def extension_tool(registry: Registry, audit: AuditSinks | None = None) -> AgentTool:
    return capability_tool(
        registry,
        "extension",
        description=(
            "插件/外部 MCP/用户钩子,kind×action:"
            " plugin list(清单与批准态)/ install(zip_path 或 source_dir,装后待用户批准)/"
            " uninstall(name,已批准须先撤销);"
            " mcp list(配置与运行态)/ preview(id,未批准也可预览);"
            " hook list(钩子文件清单)/ reload(热重载,返回 loaded/event_patterns/skipped)"
        ),
        audit=audit,
        write=True,
    )


__all__ = ["extension_tool"]
