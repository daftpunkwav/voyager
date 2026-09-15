"""Tests for tool invocation resilience, schema self-correction, and offline degradation."""

from __future__ import annotations

import httpx
from agent.llm import ToolCall
from agent.policy import AppPolicy, PolicyEngine
from agent.tools.core.base import AgentTool, Toolbelt
from agent.tools.core.invoke import validate_arguments


class TestSchemaSelfCorrection:
    def test_missing_required_argument_hint(self) -> None:
        tool = AgentTool(
            name="demo_tool",
            description="Demo",
            handler=lambda x: "ok",
            schema={
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "学习主题"},
                    "level": {"type": "integer", "description": "难度等级"},
                },
                "required": ["topic", "level"],
            },
        )
        err = validate_arguments(tool, {"topic": "math"})
        assert err is not None
        assert err.startswith("[参数错误]")
        assert "缺少必需参数 level" in err
        assert "补全缺失参数" in err

    def test_type_mismatch_correction_hint(self) -> None:
        tool = AgentTool(
            name="demo_calc",
            description="Demo",
            handler=lambda count: "ok",
            schema={
                "type": "object",
                "properties": {
                    "count": {"type": "integer", "description": "数量"},
                },
                "required": ["count"],
            },
        )
        err = validate_arguments(tool, {"count": "not-a-number"})
        assert err is not None
        assert err.startswith("[参数错误]")
        assert "需要 integer" in err
        assert "实际是 string" in err
        assert "修正 count 的类型" in err


class TestBuildingBlockResilience:
    async def test_unactivated_domain_hint_on_unknown_tool(self) -> None:
        belt = Toolbelt({}, PolicyEngine(app=AppPolicy(allowed=frozenset({"*"}))))
        out = await belt.call_detailed(ToolCall("1", "office__create_doc", {}))
        assert out.ok is False
        assert "[未知工具]" in out.text
        assert "office" in out.text
        assert "activate_tools" in out.text

    async def test_connection_refused_offline_notice(self) -> None:
        async def broken_handler() -> str:
            raise ConnectionRefusedError("Connection to 127.0.0.1:8040 refused")

        tool = AgentTool(
            name="office__get_doc",
            description="Office doc",
            handler=broken_handler,
            write=False,
        )
        belt = Toolbelt(
            {"office__get_doc": tool}, PolicyEngine(app=AppPolicy(allowed=frozenset({"*"})))
        )
        out = await belt.call_detailed(ToolCall("1", "office__get_doc", {}))
        assert out.ok is False
        assert "[积木服务离线]" in out.text
        assert "连接失败" in out.text
        assert "本地纯文本/文件工具替代" in out.text

    async def test_httpx_connect_error_offline_notice(self) -> None:
        async def http_broken() -> str:
            raise httpx.ConnectError("All connection attempts failed")

        tool = AgentTool(
            name="mcp__external__search",
            description="Remote search",
            handler=http_broken,
            write=False,
        )
        belt = Toolbelt(
            {"mcp__external__search": tool}, PolicyEngine(app=AppPolicy(allowed=frozenset({"*"})))
        )
        out = await belt.call_detailed(ToolCall("1", "mcp__external__search", {}))
        assert out.ok is False
        assert "[积木服务离线]" in out.text
        assert "连接失败" in out.text

    async def test_missing_binary_for_mcp_tool(self) -> None:
        async def binary_missing() -> str:
            raise FileNotFoundError("npx executable not found")

        tool = AgentTool(
            name="mcp__server__tool",
            description="MCP tool",
            handler=binary_missing,
            write=False,
        )
        belt = Toolbelt(
            {"mcp__server__tool": tool}, PolicyEngine(app=AppPolicy(allowed=frozenset({"*"})))
        )
        out = await belt.call_detailed(ToolCall("1", "mcp__server__tool", {}))
        assert out.ok is False
        assert "[积木服务离线]" in out.text
        assert "外部运行环境或可执行文件未找到" in out.text
