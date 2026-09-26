"""Tests for tool invocation resilience, schema self-correction, and offline degradation."""

from __future__ import annotations

import asyncio

import httpx
from agent.llm import ToolCall
from agent.mcp.session import McpRpcError
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


class TestServiceErrorContract:
    """Capability rejections surface under the pipeline's label contract:
    suffix-mapped label + message + hint, never the exception type name; and
    the deterministic rejection is not retried (no breaker accumulation)."""

    async def test_labels_map_by_suffix_and_carry_hint(self) -> None:
        from platform_contracts import ErrorSuffix, ServiceError

        def raising(message: str, hint: str):
            async def handler(**_kw: object) -> str:
                raise ServiceError("agent", ErrorSuffix.INVALID_INPUT, message, hint=hint)

            return handler

        tool = AgentTool(
            name="goal",
            description="Goal surface",
            handler=raising("unknown action: 'bogus'", "valid actions: get/set/status"),
            write=False,  # read-class path: exercises the no-retry behavior below
        )
        belt = Toolbelt({"goal": tool}, PolicyEngine(app=AppPolicy(allowed=frozenset({"*"}))))
        out = await belt.call_detailed(ToolCall("1", "goal", {"action": "bogus"}))
        assert out.ok is False
        assert out.text.startswith("[参数错误] goal: unknown action: 'bogus'")
        assert ";valid actions: get/set/status" in out.text
        assert "ServiceError" not in out.text

    async def test_forbidden_reads_as_rejected(self) -> None:
        from platform_contracts import ErrorSuffix, ServiceError

        async def guarded(**_kw: object) -> str:
            raise ServiceError(
                "agent",
                ErrorSuffix.FORBIDDEN,
                "the agent may only report done/blocked",
            )

        tool = AgentTool(name="goal", description="Goal", handler=guarded, write=True)
        belt = Toolbelt({"goal": tool}, PolicyEngine(app=AppPolicy(allowed=frozenset({"*"}))))
        out = await belt.call_detailed(ToolCall("1", "goal", {"action": "status"}))
        assert out.ok is False
        assert out.text.startswith("[已拒绝] goal: the agent may only report done/blocked")

    async def test_no_retry_on_service_error(self) -> None:
        from platform_contracts import ErrorSuffix, ServiceError

        calls = 0

        async def flaky(**_kw: object) -> str:
            nonlocal calls
            calls += 1
            raise ServiceError("agent", ErrorSuffix.INVALID_INPUT, "bad input")

        tool = AgentTool(name="observe", description="Observe", handler=flaky, write=False)
        belt = Toolbelt(
            {"observe": tool},
            PolicyEngine(app=AppPolicy(allowed=frozenset({"*"}))),
            retries=3,
            retry_backoff=0,
        )
        out = await belt.call_detailed(ToolCall("1", "observe", {}))
        assert out.ok is False
        # one attempt only: a deterministic rejection never re-runs the handler
        assert calls == 1


class TestTimeoutText:
    async def test_per_tool_timeout_reads_as_actionable_timeout(self) -> None:
        """A per-tool timeout_s expiry renders the friendly [超时] result —
        str(TimeoutError()) is empty, the generic branch showed a dangling
        colon before the dedicated branch existed."""
        calls = 0

        async def slow(**_kw: object) -> str:
            nonlocal calls
            calls += 1
            await asyncio.sleep(5)
            return "done"  # never reached: the timeout fires first

        tool = AgentTool(name="slow", description="Slow", handler=slow, timeout_s=0.05)
        belt = Toolbelt({"slow": tool}, PolicyEngine(app=AppPolicy(allowed=frozenset({"*"}))))
        out = await belt.call_detailed(ToolCall("1", "slow", {}))
        assert out.ok is False
        assert out.text.startswith("[超时] slow 在 0s 内未完成")
        assert calls == 1  # timeouts are never retried


class TestMcpFailureClasses:
    """Mounted MCP tools get the same resilience machinery as built-ins: the
    mount handler re-raises timeout/transport failures into the pipeline
    (retry + breaker + typed text) and only keeps server-decided RPC errors
    as corrective text."""

    @staticmethod
    def _mount(session, retries: int = 1) -> Toolbelt:
        from agent.mcp.mount import _build_tool

        tool = _build_tool({"id": "srv", "name": "Srv"}, session, {"name": "fetch"})
        return Toolbelt(
            {tool.name: tool},
            PolicyEngine(app=AppPolicy(allowed=frozenset({"*"}))),
            retries=retries,
            retry_backoff=0,
        )

    async def test_rpc_app_error_stays_text_and_never_trips_breaker(self) -> None:
        """A deterministic JSON-RPC error from the server is text for the model
        to correct; the breaker must stay closed (the next call goes through)."""
        calls = 0

        class _S:
            async def call_tool(self, name: str, arguments: dict) -> str:
                nonlocal calls
                calls += 1
                raise McpRpcError("JSON-RPC -32602: bad params")

        belt = self._mount(_S())
        first = await belt.call_detailed(ToolCall("1", "mcp__srv__fetch", {}))
        second = await belt.call_detailed(ToolCall("2", "mcp__srv__fetch", {}))
        assert calls == 2  # breaker stayed closed
        assert "[MCP 错误]" in first.text and "JSON-RPC -32602" in first.text
        assert "[工具失败]" not in first.text
        assert "[MCP 错误]" in second.text

    async def test_transport_failure_flows_into_retry_and_breaker(self) -> None:
        """Transport failures propagate out of the mount handler: retries apply
        (read-only surface) and enough consecutive failures open the breaker,
        which the pipeline renders as [熔断] instead of hammering the server."""
        calls = 0

        class _S:
            async def call_tool(self, name: str, arguments: dict) -> str:
                nonlocal calls
                calls += 1
                raise ConnectionError("connection reset")

        belt = self._mount(_S())
        out = await belt.call_detailed(ToolCall("1", "mcp__srv__fetch", {}))
        assert out.ok is False and calls == 2  # retried once
        assert "[积木服务离线]" in out.text
        nxt = await belt.call_detailed(ToolCall("2", "mcp__srv__fetch", {}))
        # the third attempt opens the breaker mid-call; the open circuit short-circuits
        assert nxt.text.startswith("[熔断]")
        assert calls == 3
