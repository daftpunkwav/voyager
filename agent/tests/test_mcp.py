"""End-to-end tests for external MCP: the connection layer is fully faked
(in-memory dicts, no processes, no network).

Covers: add -> preview -> unapproved invisible -> package/item approval mounting ->
Toolbelt.call reaching the Fake return value -> remove unmounting -> restart (mcp.start)
auto-reconnect -> default empty pool without domain bridges -> invalid inputs.
"""

from typing import ClassVar

import pytest
from agent.llm import FakeLLM, ToolCall
from agent.main import build_agent
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER, ServiceError

USER_CTX = ActorContext(actor=LOCAL_USER)


class FakeSession:
    """In-memory MCP server: two fixed remote tools, recording calls."""

    TOOLS: ClassVar[list[dict]] = [
        {"name": "search", "description": "Search", "schema": {"type": "object"}},
        {
            "name": "fetch",
            "description": "Fetch a remote page",
        },  # no schema -> fallback schema applies
    ]

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def list_remote_tools(self) -> list[dict]:
        return [dict(t) for t in self.TOOLS]

    async def call_tool(self, name: str, arguments: dict) -> str:
        self.calls.append((name, arguments))
        return f"fake:{name}:{arguments.get('q', '')}"

    async def aclose(self) -> None:
        self.closed = True


def fake_connect(sessions: dict[str, FakeSession], fail_ids: frozenset[str] = frozenset()):
    """connect injection point for the pool: builds a Fake session per id; ids in fail_ids fail to connect."""

    async def connect(cfg: dict) -> FakeSession:
        if cfg["id"] in fail_ids:
            raise RuntimeError("connection refused (test stub)")
        session = FakeSession()
        sessions[cfg["id"]] = session
        return session

    return connect


@pytest.fixture()
def app(tmp_path):
    sessions: dict[str, FakeSession] = {}
    app = build_agent(
        data_dir=tmp_path / "rd",
        workspace_dir=tmp_path / "ws",
        llm=FakeLLM(),
        mcp_connect=fake_connect(sessions),
    )
    app.sessions = sessions  # test handle: assert on calls the Fake received
    yield app
    app.memory.close()


async def _add(app, **overrides) -> dict:
    args = {
        "id": "demo",
        "kind": "stdio",
        "command": "npx",
        "args": ["-y", "x"],
        "approval": "item",
    }
    args.update(overrides)
    return await execute(app.registry, "add_mcp_server", USER_CTX, args)


async def _list_tools(app) -> set[str]:
    return {t["name"] for t in await execute(app.registry, "list_tools", USER_CTX, {})}


class TestAddAndPreview:
    async def test_add_previews_but_not_approved_hidden(self, app) -> None:
        """add succeeds and lists remote tools; while unapproved, list_tools and the roster have no mcp__*."""
        result = await _add(app)
        assert result["ok"] is True and result["connected"] is True
        assert {t["name"] for t in result["preview"]} == {"search", "fetch"}
        assert "mcp__demo__search" not in await _list_tools(app)
        assert not [n for n in app.spawner._toolbelt.names() if n.startswith("mcp__")]

    async def test_add_keeps_config_when_connect_fails(self, tmp_path) -> None:
        """A failed connection keeps the config: connected=False plus a readable error, ready to retry."""
        sessions: dict[str, FakeSession] = {}
        app = build_agent(
            data_dir=tmp_path / "rd",
            workspace_dir=tmp_path / "ws",
            llm=FakeLLM(),
            mcp_connect=fake_connect(sessions, fail_ids=frozenset({"bad"})),
        )
        try:
            result = await execute(
                app.registry,
                "add_mcp_server",
                USER_CTX,
                {"id": "bad", "kind": "stdio", "command": "npx"},
            )
            assert result["ok"] is True and result["connected"] is False
            assert "connection refused" in result["error"] and result["preview"] == []
            state = await execute(app.registry, "list_mcp_servers", USER_CTX, {})
            assert [s["id"] for s in state] == ["bad"]
        finally:
            app.memory.close()

    async def test_add_duplicate_id_conflict(self, app) -> None:
        await _add(app)
        with pytest.raises(ServiceError) as exc:
            await _add(app)
        assert exc.value.body.code.endswith("CONFLICT")


class TestApproveAndMount:
    async def test_package_approve_mounts_and_callable(self, app) -> None:
        """Package approval (names=['*']) -> mcp__* appears in the roster and Toolbelt.call reaches the Fake return value."""
        await _add(app)
        result = await execute(
            app.registry, "approve_mcp_tools", USER_CTX, {"id": "demo", "names": ["*"]}
        )
        assert result["approved"] == ["*"]
        assert set(result["mounted"]) == {"mcp__demo__search", "mcp__demo__fetch"}
        names = await _list_tools(app)
        assert {"mcp__demo__search", "mcp__demo__fetch"} <= names
        out = await app.spawner._toolbelt.call(
            ToolCall(id="1", name="mcp__demo__search", arguments={"q": "mcp"})
        )
        assert out == "fake:search:mcp"
        assert app.sessions["demo"].calls == [("search", {"q": "mcp"})]

    async def test_item_approve_only_selected(self, app) -> None:
        """Item approval mounts only the named tools; accumulating approvals never revokes earlier items."""
        await _add(app)
        result = await execute(
            app.registry, "approve_mcp_tools", USER_CTX, {"id": "demo", "names": ["search"]}
        )
        assert result["mounted"] == ["mcp__demo__search"]
        assert "mcp__demo__search" in await _list_tools(app)
        assert "mcp__demo__fetch" not in await _list_tools(app)
        # Approving fetch next: both present, the earlier approved search is not revoked
        result = await execute(
            app.registry, "approve_mcp_tools", USER_CTX, {"id": "demo", "names": ["fetch"]}
        )
        assert set(result["mounted"]) == {"mcp__demo__search", "mcp__demo__fetch"}

    async def test_item_approve_unknown_name_rejected(self, app) -> None:
        await _add(app)
        with pytest.raises(ServiceError) as exc:
            await execute(
                app.registry,
                "approve_mcp_tools",
                USER_CTX,
                {"id": "demo", "names": ["nonexistent-tool"]},
            )
        assert exc.value.body.code.endswith("INVALID_INPUT")

    async def test_item_approve_requires_names(self, app) -> None:
        await _add(app)
        with pytest.raises(ServiceError) as exc:
            await execute(app.registry, "approve_mcp_tools", USER_CTX, {"id": "demo"})
        assert exc.value.body.code.endswith("INVALID_INPUT")

    async def test_remount_replaces_stale_names(self, app) -> None:
        """Remounting (package) unmounts the old set first: no stale roster names, no duplicates."""
        await _add(app)
        await execute(
            app.registry, "approve_mcp_tools", USER_CTX, {"id": "demo", "names": ["search"]}
        )
        await execute(app.registry, "approve_mcp_tools", USER_CTX, {"id": "demo", "names": ["*"]})
        mcp_names = [n for n in await _list_tools(app) if n.startswith("mcp__")]
        assert sorted(mcp_names) == ["mcp__demo__fetch", "mcp__demo__search"]


class TestAppDimension:
    """Mounted with dimension="app": calls share the same agent.app.allowed/denied lists as bridge tools;
    approval is only the gate into the roster. Lists change hot via set_setting (PolicyEngine holds a settings handle)."""

    async def _approve_all(self, app) -> None:
        await _add(app)
        await execute(app.registry, "approve_mcp_tools", USER_CTX, {"id": "demo", "names": ["*"]})

    async def test_mounted_dimension_is_app(self, app) -> None:
        await self._approve_all(app)
        assert app.spawner._toolbelt._tools["mcp__demo__search"].dimension == "app"

    async def test_allow_list_without_mcp_rejects_before_handler(self, app) -> None:
        """Once the allow list narrows to notes__*, mcp__* is rejected and the remote handler never runs."""
        await self._approve_all(app)
        await execute(
            app.registry,
            "set_setting",
            USER_CTX,
            {"key": "agent.app.allowed", "value": ["notes__*"]},
        )
        out = await app.spawner._toolbelt.call(
            ToolCall(id="1", name="mcp__demo__search", arguments={"q": "x"})
        )
        assert "[已拒绝]" in out
        assert app.sessions["demo"].calls == []

    async def test_allow_mcp_prefix_still_calls_fake(self, app) -> None:
        await self._approve_all(app)
        await execute(
            app.registry,
            "set_setting",
            USER_CTX,
            {"key": "agent.app.allowed", "value": ["mcp__*"]},
        )
        out = await app.spawner._toolbelt.call(
            ToolCall(id="1", name="mcp__demo__search", arguments={"q": "mcp"})
        )
        assert out == "fake:search:mcp"
        assert app.sessions["demo"].calls == [("search", {"q": "mcp"})]

    async def test_denied_mcp_prefix_wins_over_allowed_star(self, app) -> None:
        """allowed=["*"] + denied=["mcp__*"]: deny wins and the handler never runs."""
        await self._approve_all(app)
        await execute(
            app.registry,
            "set_setting",
            USER_CTX,
            {"key": "agent.app.denied", "value": ["mcp__*"]},
        )
        out = await app.spawner._toolbelt.call(
            ToolCall(id="1", name="mcp__demo__search", arguments={"q": "x"})
        )
        assert "[已拒绝]" in out
        assert app.sessions["demo"].calls == []


class TestRemove:
    async def test_remove_unmounts_and_forgets(self, app) -> None:
        await _add(app)
        await execute(app.registry, "approve_mcp_tools", USER_CTX, {"id": "demo", "names": ["*"]})
        session = app.sessions["demo"]
        await execute(app.registry, "remove_mcp_server", USER_CTX, {"id": "demo"})
        assert not [n for n in await _list_tools(app) if n.startswith("mcp__")]
        out = await app.spawner._toolbelt.call(
            ToolCall(id="2", name="mcp__demo__search", arguments={})
        )
        assert "未知工具" in out
        state = await execute(app.registry, "list_mcp_servers", USER_CTX, {})
        assert state == []
        assert session.closed  # the session was closed

    async def test_remove_unknown_not_found(self, app) -> None:
        with pytest.raises(ServiceError) as exc:
            await execute(app.registry, "remove_mcp_server", USER_CTX, {"id": "ghost"})
        assert exc.value.body.code.endswith("NOT_FOUND")


class TestRestart:
    async def test_start_reconnects_approved(self, tmp_path) -> None:
        """Settings pre-seeded with approved=['*'] -> a fresh build_agent plus mcp.start() mounts automatically."""
        from platform_settings import SettingsStore

        shared = SettingsStore(tmp_path / "shared.db")
        sessions: dict[str, FakeSession] = {}
        cfg = {
            "id": "demo",
            "name": "demo",
            "kind": "stdio",
            "command": "npx",
            "args": [],
            "url": "",
            "approval": "package",
            "approved": ["*"],
            "enabled": True,
        }
        app = build_agent(
            data_dir=tmp_path / "rd",
            workspace_dir=tmp_path / "ws",
            llm=FakeLLM(),
            settings_store=shared,
            mcp_connect=fake_connect(sessions),
        )
        await shared.set(
            "agent.mcp.servers", [cfg], LOCAL_USER
        )  # the key is already registered by build
        try:
            assert not [n for n in app.spawner._toolbelt.names() if n.startswith("mcp__")]
            await app.mcp.start()
            assert "mcp__demo__search" in app.spawner._toolbelt.names()
            # Idempotent: repeated start neither crashes nor duplicates
            await app.mcp.start()
            names = [n for n in app.spawner._toolbelt.names() if n.startswith("mcp__")]
            assert len(names) == 2
        finally:
            app.close()
            shared.close()

    async def test_preview_remounts_after_start_failure(self, tmp_path) -> None:
        """If startup cannot connect, preview remounts per the saved approval once fixed, with no re-approval needed."""
        from platform_settings import SettingsStore

        shared = SettingsStore(tmp_path / "shared.db")
        sessions: dict[str, FakeSession] = {}
        fail_ids = {"broken"}

        async def flaky_connect(cfg: dict) -> FakeSession:
            if cfg["id"] in fail_ids:
                raise RuntimeError("connection refused (test stub)")
            session = FakeSession()
            sessions[cfg["id"]] = session
            return session

        app = build_agent(
            data_dir=tmp_path / "rd",
            workspace_dir=tmp_path / "ws",
            llm=FakeLLM(),
            settings_store=shared,
            mcp_connect=flaky_connect,
        )
        await shared.set(
            "agent.mcp.servers",
            [
                {
                    "id": "broken",
                    "name": "b",
                    "kind": "stdio",
                    "command": "npx",
                    "args": [],
                    "url": "",
                    "approval": "package",
                    "approved": ["*"],
                    "enabled": True,
                }
            ],
            LOCAL_USER,
        )
        try:
            await app.mcp.start()
            assert "mcp__broken__search" not in app.spawner._toolbelt.names()
            fail_ids.clear()
            await execute(app.registry, "preview_mcp_tools", USER_CTX, {"id": "broken"})
            assert "mcp__broken__search" in app.spawner._toolbelt.names()
        finally:
            app.close()
            shared.close()

    async def test_start_skips_unapproved_and_records_failure(self, tmp_path) -> None:
        """Enabled but unapproved entries do not connect; approved-but-failing entries record an error without blocking startup."""
        from platform_settings import SettingsStore

        shared = SettingsStore(tmp_path / "shared.db")
        sessions: dict[str, FakeSession] = {}
        app = build_agent(
            data_dir=tmp_path / "rd",
            workspace_dir=tmp_path / "ws",
            llm=FakeLLM(),
            settings_store=shared,
            mcp_connect=fake_connect(sessions, fail_ids=frozenset({"broken"})),
        )
        await shared.set(
            "agent.mcp.servers",
            [
                {
                    "id": "draft",
                    "name": "d",
                    "kind": "stdio",
                    "command": "npx",
                    "args": [],
                    "url": "",
                    "approval": "item",
                    "approved": [],
                    "enabled": True,
                },
                {
                    "id": "broken",
                    "name": "b",
                    "kind": "stdio",
                    "command": "npx",
                    "args": [],
                    "url": "",
                    "approval": "package",
                    "approved": ["*"],
                    "enabled": True,
                },
            ],
            LOCAL_USER,
        )
        try:
            await app.mcp.start()
            assert "draft" not in sessions  # unapproved: no connection
            state = {s["id"]: s for s in app.mcp.list_state()}
            assert state["draft"]["connected"] is False
            assert state["broken"]["connected"] is False
            assert "connection refused" in state["broken"]["error"]
        finally:
            app.memory.close()
            shared.close()

    async def test_start_rejects_invalid_config_without_connect(self, tmp_path) -> None:
        """Dirty configs written straight into settings (file: url / empty command):
        start validates before connect; valid entries are unaffected."""
        from platform_settings import SettingsStore

        shared = SettingsStore(tmp_path / "shared.db")
        sessions: dict[str, FakeSession] = {}
        app = build_agent(
            data_dir=tmp_path / "rd",
            workspace_dir=tmp_path / "ws",
            llm=FakeLLM(),
            settings_store=shared,
            mcp_connect=fake_connect(sessions),
        )
        await shared.set(
            "agent.mcp.servers",
            [
                {
                    "id": "dirty-url",
                    "name": "du",
                    "kind": "url",
                    "url": "file:///etc/passwd",
                    "command": "",
                    "args": [],
                    "approval": "package",
                    "approved": ["*"],
                    "enabled": True,
                },
                {
                    "id": "dirty-cmd",
                    "name": "dc",
                    "kind": "stdio",
                    "command": "",
                    "args": [],
                    "url": "",
                    "approval": "package",
                    "approved": ["*"],
                    "enabled": True,
                },
                {
                    "id": "ok",
                    "name": "ok",
                    "kind": "stdio",
                    "command": "npx",
                    "args": [],
                    "url": "",
                    "approval": "package",
                    "approved": ["*"],
                    "enabled": True,
                },
            ],
            LOCAL_USER,
        )
        try:
            await app.mcp.start()
            assert "dirty-url" not in sessions  # dirty configs never reach connect
            assert "dirty-cmd" not in sessions
            assert "ok" in sessions  # valid entries mount as usual
            state = {s["id"]: s for s in app.mcp.list_state()}
            assert "file" in state["dirty-url"]["error"]
            assert state["dirty-cmd"]["error"]
            assert not [n for n in app.spawner._toolbelt.names() if n.startswith("mcp__dirty-")]
        finally:
            app.close()
            shared.close()

    async def test_start_skips_config_without_id(self, tmp_path) -> None:
        """A dirty entry missing its id, written straight into settings: start neither raises nor blocks
        the valid servers after it; list_state neither raises nor contains empty-id rows. Dirty
        entries are not auto-cleaned."""
        from platform_settings import SettingsStore

        shared = SettingsStore(tmp_path / "shared.db")
        sessions: dict[str, FakeSession] = {}
        app = build_agent(
            data_dir=tmp_path / "rd",
            workspace_dir=tmp_path / "ws",
            llm=FakeLLM(),
            settings_store=shared,
            mcp_connect=fake_connect(sessions),
        )
        await shared.set(
            "agent.mcp.servers",
            [
                {
                    "name": "no-id",
                    "kind": "stdio",
                    "command": "npx",
                    "args": [],
                    "url": "",
                    "approval": "package",
                    "approved": ["*"],
                    "enabled": True,
                },  # dirty entry without an id (leftover from a direct write)
                {
                    "id": "ok",
                    "name": "ok",
                    "kind": "stdio",
                    "command": "npx",
                    "args": [],
                    "url": "",
                    "approval": "package",
                    "approved": ["*"],
                    "enabled": True,
                },
            ],
            LOCAL_USER,
        )
        try:
            await app.mcp.start()  # missing id must not raise
            assert list(sessions) == [
                "ok"
            ]  # the dirty entry stays out of sessions; the valid one connects
            assert "mcp__ok__search" in app.spawner._toolbelt.names()
            state = app.mcp.list_state()  # missing id must not raise
            assert [s["id"] for s in state if s["id"] == "ok"] == ["ok"]
            assert all(str(s.get("id") or "").strip() for s in state)  # no empty-id rows
        finally:
            app.close()
            shared.close()


class TestDefaultEmpty:
    async def test_default_pool_empty_no_domain_bridge(self, tmp_path) -> None:
        """Default assembly (no start, no configs) leaves the pool empty; domain bridges never appear under MCP names."""
        app = build_agent(
            data_dir=tmp_path / "rd",
            workspace_dir=tmp_path / "ws",
            llm=FakeLLM(),
        )
        try:
            assert app.mcp.list_state() == []
            names = app.spawner._toolbelt.names()
            assert not [n for n in names if n.startswith("mcp__")]
        finally:
            app.memory.close()


class TestInvalidInput:
    async def test_bad_id_rejected(self, app) -> None:
        with pytest.raises(ServiceError) as exc:
            await _add(app, id="Bad_ID")
        assert exc.value.body.code.endswith("INVALID_INPUT")

    async def test_file_url_rejected(self, app) -> None:
        with pytest.raises(ServiceError) as exc:
            await _add(app, id="u1", kind="url", url="file:///etc/passwd")
        assert exc.value.body.code.endswith("INVALID_INPUT")

    async def test_empty_command_rejected(self, app) -> None:
        with pytest.raises(ServiceError) as exc:
            await _add(app, id="s1", kind="stdio", command="  ")
        assert exc.value.body.code.endswith("INVALID_INPUT")


class TestDomains:
    def test_mcp_domain_activatable(self) -> None:
        """Once mcp__* appears in the roster the derived domains include mcp, letting Lucien activate_tools(domain='mcp')
        to see approved tools; with an empty roster or no mcp tools it is absent (derived, not a constant)."""
        from agent.tools.core.activate import CORE_TOOLS, domain_prefixes

        assert "mcp" in domain_prefixes(["mcp__demo__search", "read_file"])
        assert "mcp" not in domain_prefixes(["read_file", "notes__create_note"])
        assert domain_prefixes([]) == ()
        assert "load_skill" in CORE_TOOLS  # must never leave CORE
        assert not [n for n in CORE_TOOLS if n.startswith("mcp__")]


class ResourceSession(FakeSession):
    """Fake server with the resources capability and declared instructions."""

    TOOLS: ClassVar[list[dict]] = [
        {"name": "search", "description": "Search", "schema": {"type": "object"}},
    ]

    def __init__(self) -> None:
        super().__init__()
        self.server_capabilities: dict = {"tools": {}, "resources": {}}
        self.instructions: str = "Always quote resource URIs verbatim."
        self.reads: list[str] = []

    async def list_resources(self) -> list[dict]:
        return [
            {"uri": "file:///docs/readme.md", "name": "readme", "description": "The readme"},
            {
                "uri": "file:///data/blob.bin",
                "name": "blob",
                "mimeType": "application/octet-stream",
            },
        ]

    async def read_resource(self, uri: str) -> str:
        self.reads.append(uri)
        if uri == "file:///data/blob.bin":
            return "[non-text content: application/octet-stream]"
        return "hello from resource"


def resource_connect(sessions: dict[str, FakeSession]):
    async def connect(cfg: dict) -> FakeSession:
        session = ResourceSession()
        sessions[cfg["id"]] = session
        return session

    return connect


class TestHotRefreshAndResources:
    @pytest.fixture()
    def rapp(self, tmp_path):
        sessions: dict[str, FakeSession] = {}
        app = build_agent(
            data_dir=tmp_path / "rd",
            workspace_dir=tmp_path / "ws",
            llm=FakeLLM(),
            mcp_connect=resource_connect(sessions),
        )
        app.sessions = sessions
        yield app
        app.memory.close()

    async def _mount_all(self, app) -> None:
        await _add(app, id="demo", kind="url", url="https://mcp.example.test")
        await execute(
            app.registry,
            "approve_mcp_tools",
            USER_CTX,
            {"id": "demo", "names": ["*"]},
        )
        await app.mcp.preview("demo")

    async def test_resource_tools_mounted_under_star_approval(self, rapp) -> None:
        await self._mount_all(rapp)
        names = rapp.mcp._toolbelt.names()
        assert "mcp__demo__list_resources" in names
        assert "mcp__demo__read_resource" in names
        out = await rapp.mcp._toolbelt.call(
            ToolCall("1", "mcp__demo__read_resource", {"uri": "file:///docs/readme.md"})
        )
        assert "hello from resource" in out
        out = await rapp.mcp._toolbelt.call(ToolCall("2", "mcp__demo__list_resources", {}))
        assert "file:///docs/readme.md" in out

    async def test_resource_tools_absent_without_coverage(self, rapp) -> None:
        await _add(rapp, id="demo", kind="url", url="https://mcp.example.test")
        await execute(
            rapp.registry,
            "approve_mcp_tools",
            USER_CTX,
            {"id": "demo", "names": ["search"]},  # explicit tool, no resource coverage
        )
        await rapp.mcp.preview("demo")
        names = rapp.mcp._toolbelt.names()
        assert "mcp__demo__search" in names
        assert "mcp__demo__list_resources" not in names
        assert "mcp__demo__read_resource" not in names

    async def test_instructions_captured_and_sorted(self, rapp) -> None:
        assert rapp.mcp.instructions_map() == {}
        await self._mount_all(rapp)
        assert rapp.mcp.instructions_map() == {"demo": "Always quote resource URIs verbatim."}

    async def test_refresh_picks_up_new_remote_tools(self, rapp) -> None:
        await self._mount_all(rapp)
        assert "mcp__demo__fresh" not in rapp.mcp._toolbelt.names()
        rapp.sessions["demo"].TOOLS.append({"name": "fresh", "description": "New tool"})
        await rapp.mcp.refresh_approved()
        assert "mcp__demo__fresh" in rapp.mcp._toolbelt.names()

    async def test_refresh_failure_records_error_keeps_session_dropped(self, rapp) -> None:
        await self._mount_all(rapp)

        # make the re-list fail: refresh records the error and drops the session
        async def _boom():
            raise RuntimeError("remote exploded")

        rapp.sessions["demo"].list_remote_tools = _boom
        await rapp.mcp.refresh_approved()
        state = {s["id"]: s for s in rapp.mcp.list_state()}
        assert state["demo"]["error"] != ""
        assert "demo" not in rapp.mcp._sessions  # session dropped on failed refresh
        # the mount lingers (existing pool semantics on connection loss)

    def test_builder_renders_mcp_section(self) -> None:
        from agent.context.builder import ContextBuilder

        builder = ContextBuilder(rules=["r1"])
        text = builder.system(mcp_section="【MCP: a】\nuse it well")
        assert "【MCP: a】" in text and "use it well" in text
        assert "【MCP" not in builder.system()
