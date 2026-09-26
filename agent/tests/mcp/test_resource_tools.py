"""Tests for MCP resource tools (list_resources / read_resource) and the
remount approval gate: only server-decided RPC errors become corrective text,
transport failures propagate into the tool pipeline, and the approval list —
not capability discovery — decides what mounts."""

from typing import Any, cast

from agent.mcp.mount import _build_tool, _resource_tools, remount
from agent.mcp.session import McpSession
from agent.policy import AppPolicy, PolicyEngine
from agent.tools.core.base import Toolbelt


class _FakeSession:
    """Minimal McpSession stand-in: only the members a test configures."""

    def __init__(
        self,
        *,
        resources: list[dict] | None = None,
        error: Exception | None = None,
        capabilities: dict | None = None,
        with_resource_methods: bool = True,
    ) -> None:
        self.server_capabilities = capabilities if capabilities is not None else {}
        if not with_resource_methods:
            # mount.py probes with getattr(session, "list_resources", None):
            # instances without the methods read as "no resource support"
            self.list_resources = None  # type: ignore[assignment, method-assign]
            self.read_resource = None  # type: ignore[assignment, method-assign]
            return
        if resources is None and error is None:
            resources = []
        self._resources = resources
        self._error = error

    async def list_resources(self) -> list[dict]:
        if self._error is not None:
            raise self._error
        return self._resources or []

    async def read_resource(self, uri: str) -> str:
        if self._error is not None:
            raise self._error
        return f"content of {uri}"


def _belt_with(tools: dict) -> Toolbelt:
    return Toolbelt(tools, PolicyEngine(app=AppPolicy(allowed=frozenset({"*"}))))


class TestResourceToolErrorClasses:
    async def test_missing_resource_methods_read_as_failed_text(self) -> None:
        session = _FakeSession(with_resource_methods=False)
        caps = _resource_tools({"id": "srv", "name": "Srv"}, cast(McpSession, session))
        belt = _belt_with(caps)
        listed = await belt.call_detailed(
            type("C", (), {"id": "1", "name": "mcp__srv__list_resources", "arguments": {}})()
        )
        assert "server has no resources" in listed.text

    async def test_rpc_error_reads_as_corrective_text(self) -> None:
        from agent.mcp.session import McpRpcError

        session = _FakeSession(error=McpRpcError("JSON-RPC -32601: no such method"))
        caps = _resource_tools({"id": "srv", "name": "Srv"}, cast(McpSession, session))
        belt = _belt_with(caps)
        listed = await belt.call_detailed(
            type("C", (), {"id": "1", "name": "mcp__srv__list_resources", "arguments": {}})()
        )
        assert "[MCP 错误]" in listed.text and "JSON-RPC -32601" in listed.text
        read = await belt.call_detailed(
            type(
                "C",
                (),
                {"id": "2", "name": "mcp__srv__read_resource", "arguments": {"uri": "u://x"}},
            )()
        )
        assert "[MCP 错误]" in read.text

    async def test_success_formats_resources_and_reads_content(self) -> None:
        session = _FakeSession(
            resources=[
                {"uri": "u://a", "name": "Alpha"},
                {"uri": "u://b", "name": "Beta", "description": "second"},
            ]
        )
        caps = _resource_tools({"id": "srv", "name": "Srv"}, cast(McpSession, session))
        belt = _belt_with(caps)
        listed = await belt.call_detailed(
            type("C", (), {"id": "1", "name": "mcp__srv__list_resources", "arguments": {}})()
        )
        assert "u://a" in listed.text and "Alpha" in listed.text and "second" in listed.text
        read = await belt.call_detailed(
            type(
                "C",
                (),
                {"id": "2", "name": "mcp__srv__read_resource", "arguments": {"uri": "u://a"}},
            )()
        )
        assert "content of u://a" in read.text


class TestRemountApprovalGate:
    def _remount(self, session: Any, approved: list[str]) -> list[str]:
        belt = Toolbelt({}, PolicyEngine(app=AppPolicy(allowed=frozenset({"*"}))))
        return remount(
            belt,
            {"id": "srv", "name": "Srv"},
            cast(McpSession, session),
            [{"name": "fetch", "description": "d"}, {"name": "send", "description": "d"}],
            approved,
        )

    def test_star_approval_mounts_tools_and_resource_pair(self) -> None:
        session = _FakeSession(capabilities={"resources": {}})
        session2 = _FakeSession(capabilities={"resources": {}})
        belt = Toolbelt({}, PolicyEngine(app=AppPolicy(allowed=frozenset({"*"}))))
        names = remount(
            belt,
            {"id": "srv", "name": "Srv"},
            cast(McpSession, session),
            [{"name": "fetch"}],
            ["*"],
        )
        assert names == ["mcp__srv__fetch", "mcp__srv__list_resources", "mcp__srv__read_resource"]
        # resources: declared capability gates the synthesized pair in
        belt2 = Toolbelt({}, PolicyEngine(app=AppPolicy(allowed=frozenset({"*"}))))
        names2 = remount(
            belt2,
            {"id": "srv", "name": "Srv"},
            cast(McpSession, session2),
            [{"name": "fetch"}],
            ["*"],
        )
        assert "mcp__srv__read_resource" in names2

    def test_capability_absent_blocks_resource_pair_even_under_star(self) -> None:
        session = _FakeSession(capabilities={"tools": {}})  # server declares no resources
        names = self._remount(session, ["*"])
        assert names == ["mcp__srv__fetch", "mcp__srv__send"]
        assert not any("resource" in n for n in names)

    def test_explicit_approval_selects_only_named_tools(self) -> None:
        session = _FakeSession(capabilities={"resources": {}})
        names = self._remount(session, ["fetch"])
        assert names == ["mcp__srv__fetch"]

    def test_unmount_first_removes_stale_names(self) -> None:
        session = _FakeSession(capabilities={"resources": {}})
        belt = Toolbelt({}, PolicyEngine(app=AppPolicy(allowed=frozenset({"*"}))))
        remount(
            belt,
            {"id": "srv", "name": "Srv"},
            cast(McpSession, session),
            [{"name": "fetch"}],
            ["*"],
        )
        stale = _build_tool(
            {"id": "srv", "name": "Srv"}, cast(McpSession, session), {"name": "fetch"}
        )
        belt.register({stale.name: stale})
        remount(
            belt,
            {"id": "srv", "name": "Srv"},
            cast(McpSession, session),
            [{"name": "fetch"}],
            ["fetch"],
        )
        assert belt.names() == ["mcp__srv__fetch"]
