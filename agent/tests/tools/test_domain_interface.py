"""Pins the domain tool integration contract (docs-local/phases/14):
a domain package plugs into the agent through ToolSource / extra_tools with
`<domain>__<capability>` naming, becomes visible to list_tools, and honors
prefix-trim + graded domain activation. Domain packages must fit this contract;
nothing else may be wired.
"""

from agent.llm import FakeLLM
from agent.main import build_agent
from agent.tools import AgentTool, StaticToolSource, ToolRegistry
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER

USER_CTX = ActorContext(actor=LOCAL_USER)


def _domain_tools() -> dict[str, AgentTool]:
    async def create_note(title: str = "", content: str = "") -> dict:
        return {"title": title, "content": content}

    def get_note(note_id: str = "") -> str:
        return f"note {note_id}"

    return {
        "notes__create_note": AgentTool(
            name="notes__create_note",
            description="创建笔记",
            handler=create_note,
            dimension="app",
            write=True,
            schema={
                "type": "object",
                "properties": {"title": {"type": "string"}, "content": {"type": "string"}},
                "required": ["title"],
            },
        ),
        "notes__get_note": AgentTool(
            name="notes__get_note",
            description="读笔记",
            handler=get_note,
            dimension="app",
            concurrent_safe=True,
            schema={"type": "object", "properties": {"note_id": {"type": "string"}}},
        ),
    }


class TestToolSourceContract:
    def test_static_source_into_registry(self) -> None:
        """A domain package wraps its tools in a ToolSource; ToolRegistry
        merges by source order and records origins."""
        registry = ToolRegistry()
        registry.add(StaticToolSource("fs-note-like", {}))
        registry.add(StaticToolSource("notes", _domain_tools()))
        tools = registry.build()
        assert "notes__create_note" in tools and "notes__get_note" in tools
        origins = registry.origins()
        assert origins["notes__create_note"] == "notes"


class TestDomainWiring:
    def _app(self, tmp_path):
        app = build_agent(
            data_dir=tmp_path / "rd",
            workspace_dir=tmp_path / "ws",
            llm=FakeLLM(),
            extra_tools=_domain_tools(),
        )
        return app

    def test_extra_tools_reach_roster_and_list_tools(self, tmp_path) -> None:
        """The injected domain bridge is the only channel a domain package
        needs: tools land in the roster and the list_tools capability (the
        human surface) sees them."""
        app = self._app(tmp_path)
        try:
            belt = app.spawner._toolbelt
            assert "notes__create_note" in belt.names()
            specs = {s.name for s in belt.specs()}
            assert "notes__get_note" in specs
        finally:
            app.close()

    async def test_list_tools_capability_lists_domain_tools(self, tmp_path) -> None:
        app = self._app(tmp_path)
        try:
            out = await execute(app.registry, "tools", USER_CTX, {"action": "list"})
            names = {t["name"] for t in out}
            assert "notes__create_note" in names
        finally:
            app.close()

    def test_prefix_trim_and_readonly_narrow(self, tmp_path) -> None:
        """Dispatch-time narrowing works on domain tools by the same rules:
        prefix grants (`notes__*`), and read-only trims drop write tools by
        metadata, not by name list."""
        app = self._app(tmp_path)
        try:
            belt = app.spawner._toolbelt
            trimmed = belt.trimmed(["echo__*", "notes__*"])
            assert "notes__create_note" in trimmed.names()
            readonly = belt.trimmed_read_only()
            assert "notes__get_note" in readonly.names()
            assert "notes__create_note" not in readonly.names()  # write=True dropped
        finally:
            app.close()

    def test_domain_activation_makes_schema_visible(self, tmp_path) -> None:
        """Graded loading: domain tools stay out of round-one specs; after
        activate_tools(domain=...) the next specs() carries them."""
        from agent.tools import CORE_TOOLS, graded_toolbelt

        app = self._app(tmp_path)
        try:
            belt = app.spawner._toolbelt
            active: set[str] = set(CORE_TOOLS)
            graded = graded_toolbelt(belt, active)
            first = {s.name for s in graded.specs()}
            assert "notes__create_note" not in first
            # activate_tools(domain="notes") merges matching names into the
            # shared activation set (same mutation the tool handler performs)
            active.update(n for n in belt.names() if n.startswith("notes__"))
            second = {s.name for s in graded.specs()}
            assert "notes__create_note" in second
        finally:
            app.close()
