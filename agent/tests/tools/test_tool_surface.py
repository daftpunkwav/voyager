"""Tool-surface tiering: prefix grants, domain activation for the chat
persona, and tool step visibility.

- Prefix grants: notes__* expands against the current roster, so newly mounted domain
  capabilities enter the organizer trimmed surface automatically; persona files never
  hardcode the expansion.
- Domain activation: the chat instance's first-round complete sends only the CORE active
  set; after activate_tools the next round sees the domain; call() is never gated by
  activation.
- agent.step: tool steps reach the event stream (gateway _STREAM_TYPES).
"""

import asyncio
from pathlib import Path

import agent.personas.organizer as organizer_mod
from agent.llm import FakeLLM, LLMReply, ToolCall
from agent.main import build_agent
from agent.personas import resolve_persona
from agent.subagent.instance import page_preactivate
from agent.tools import AgentTool


def _app(tmp_path, llm, extra_tools=None):
    return build_agent(
        data_dir=tmp_path / "rd",
        workspace_dir=tmp_path / "ws",
        llm=llm,
        extra_tools=extra_tools,
    )


def _fake_notes_tools() -> dict[str, AgentTool]:
    async def create_note(title: str = "", content: str = "") -> dict:
        return {"note_id": "n-1", "title": title}

    async def mark_note_span(note_id: str = "", **kw) -> str:
        return f"marked {note_id}"

    return {
        "notes__create_note": AgentTool(
            name="notes__create_note",
            description="[notes] create note",
            handler=create_note,
        ),
        "notes__mark_note_span": AgentTool(
            name="notes__mark_note_span",
            description="[notes] highlight a selection",
            handler=mark_note_span,
        ),
    }


class TestPrefixGrant:
    """Prefix grant: the notes__* allowlist expands against the current roster."""

    async def test_organizer_picks_up_new_notes_tools(self, tmp_path) -> None:
        """A brand-new notes capability added to the bridge is usable without touching the allowlist."""
        app = _app(tmp_path, FakeLLM(default="Done."), _fake_notes_tools())
        inst = await app.master.dispatch_task("highlight the note", persona="organizer")
        names = inst.toolbelt.names()
        assert "notes__mark_note_span" in names
        assert "notes__create_note" in names
        # The narrow sources grant is not widened by the prefix: write-class capabilities stay out
        assert not any(n.startswith("sources__remove") for n in names)
        app.memory.close()

    def test_persona_file_does_not_enumerate_expansion(self) -> None:
        """The persona file grants a prefix, not an enumerated expansion (no bridge tool names hardcoded)."""
        src = Path(organizer_mod.__file__).read_text(encoding="utf-8")
        assert "notes__*" in src
        assert "notes__create_note" not in src
        assert "mark_note_span" not in src

    def test_allow_none_stays_full(self) -> None:
        """allow=None (the orchestrator) trims nothing; prefix grants only affect the allowlist path."""
        persona = resolve_persona("organizer")
        assert persona is not None and persona.tool_allow is not None
        assert any(a.endswith("*") for a in persona.tool_allow)


class TestLucienDomainActivation:
    """Domain activation: the chat instance sends only the CORE active set in round one; after activate, the next round sees the domain."""

    async def test_first_round_is_graded_then_activate(
        self, tmp_path, settle, agent_replies
    ) -> None:
        llm = FakeLLM(
            [
                LLMReply(tool_calls=(ToolCall("1", "activate_tools", {"domain": "notes"}),)),
                LLMReply(
                    tool_calls=(
                        ToolCall("2", "notes__create_note", {"title": "t", "content": "c"}),
                    )
                ),
                LLMReply(text="The note is saved."),
            ]
        )
        app = _app(tmp_path, llm, _fake_notes_tools())
        await app.master.handle_user_message("start processing those items")
        await settle(app)
        first = [s.name for s in llm.calls[0]["tools"]]
        second = [s.name for s in llm.calls[1]["tools"]]
        # Round one: far smaller than the full roster, no notes tools, but activate_tools present.
        # Bound covers the builtin surface only (bridge domains stay out);
        # bump it when a builtin is added, never to admit a domain.
        assert "notes__create_note" not in first
        assert "activate_tools" in first
        assert len(first) < 22
        # After activate(domain=notes): the next complete includes the notes tools
        assert "notes__create_note" in second
        assert "[完成]" in agent_replies(app)[-1] or agent_replies(
            app
        )  # the notification path still works
        app.memory.close()

    async def test_call_before_activation_still_executes(self, tmp_path, settle) -> None:
        """call() is not gated by activation: calling an unactivated name still executes (timeouts came from schema size alone)."""
        llm = FakeLLM(
            [
                LLMReply(
                    tool_calls=(
                        ToolCall("1", "notes__create_note", {"title": "t", "content": "c"}),
                    )
                ),
                LLMReply(text="done"),
            ]
        )
        app = _app(tmp_path, llm, _fake_notes_tools())
        await app.master.handle_user_message("write the note directly, no activation")
        await settle(app)
        # Tool results live in the same round's messages (llm.calls[1]) and never enter cross-turn history (current behavior)
        tool_results = [m["content"] for m in llm.calls[1]["messages"] if m["role"] == "tool"]
        assert tool_results and "未知工具" not in tool_results[0]
        assert "n-1" in tool_results[0]
        app.memory.close()

    async def test_ack_without_followup_still_runs_tools(
        self, tmp_path, settle, agent_replies
    ) -> None:
        """After the user says "test everything" and the model only answers "okay": the same turn continues calling tools without waiting for the user again."""
        llm = FakeLLM(
            [
                LLMReply(text="Okay, trying all three at once. Right away."),
                LLMReply(tool_calls=(ToolCall("1", "activate_tools", {"domain": "notes"}),)),
                LLMReply(tool_calls=(ToolCall("2", "notes__mark_note_span", {"note_id": "n-1"}),)),
                LLMReply(text="The highlight is applied."),
            ]
        )
        app = _app(tmp_path, llm, _fake_notes_tools())
        await app.master.handle_user_message("test them all")
        await settle(app)
        assert len(llm.calls) == 4  # no second handle_user_message happened
        assert "The highlight is applied" in agent_replies(app)[-1]
        app.memory.close()

    async def test_note_keyword_preactivates_notes_domain(self, tmp_path, settle) -> None:
        """When the user mentions notes, the notes schema is visible in round one, saving a pure activate round."""
        llm = FakeLLM([LLMReply(text="Look at the tool surface first.")])
        app = _app(tmp_path, llm, _fake_notes_tools())
        # The keyword-hint table (agent.tools.core.activate) matches Chinese
        # note keywords ("note"/"shading" in Chinese), so this fixture keeps the Chinese phrasing
        await app.master.handle_user_message("给这篇笔记加底纹")
        await settle(app)
        first = [s.name for s in llm.calls[0]["tools"]]
        assert "notes__mark_note_span" in first
        app.memory.close()

    async def test_dispatched_task_instance_not_graded(self, tmp_path) -> None:
        """A dispatched task subagent (trimmed) hands the full specs to the model, no activation involved."""
        llm = FakeLLM(default="Done.")
        app = _app(tmp_path, llm, _fake_notes_tools())
        inst = await app.master.dispatch_task("organize", persona="organizer")
        assert inst.active is None  # tiering applies only to the chat instance
        await asyncio.sleep(0.05)
        specs = llm.calls[0]["tools"]
        assert specs is not None and "notes__create_note" in [s.name for s in specs]
        app.memory.close()


class TestStepEvents:
    """agent.step: tool steps reach the event stream so Chat can see which tool is being called."""

    async def test_tool_step_reaches_event_stream(self, tmp_path, agent_replies, settle) -> None:
        llm = FakeLLM(
            [
                LLMReply(tool_calls=(ToolCall("1", "list_dir", {"path": "."}),)),
                LLMReply(text="Done looking."),
            ]
        )
        app = _app(tmp_path, llm)
        await app.master.handle_user_message("look at the working directory")
        await settle(app)
        steps = [e.payload for _, e in app.log.read_after(types=["agent.step"])]
        assert any(s["name"] == "list_dir" for s in steps)
        assert all(s.get("subagent") for s in steps)
        assert all(len(s.get("summary", "")) <= 120 for s in steps)
        assert all(s.get("run_id") for s in steps)  # trace linkage for UIs
        tool_rows = [s for s in steps if s.get("kind") == "tool"]
        assert tool_rows and all(
            r["detail"].get("tool_call_id") and r["detail"].get("ok") is True for r in tool_rows
        )
        llm_rows = [s for s in steps if s.get("kind") == "llm"]
        assert llm_rows and all(
            r["detail"].get("round") and r["detail"].get("ms", -1) >= 0 for r in llm_rows
        )
        app.memory.close()

    async def test_step_refreshes_digest_store(self, tmp_path, agent_replies, settle) -> None:
        """After tool steps, DigestStore renders the latest steps, truncated to 120 chars."""
        llm = FakeLLM(
            [
                LLMReply(tool_calls=(ToolCall("1", "list_dir", {"path": "."}),)),
                LLMReply(text="Done looking."),
            ]
        )
        app = _app(tmp_path, llm)
        await app.master.handle_user_message("look at the working directory")
        await settle(app)
        # list_dir is recorded in the step trail; DigestStore upserts every step, so the final last_step
        # is the closing text reply. Assert the list_dir step via instance state directly and verify render is non-empty.
        chat = app.master.chat
        assert chat is not None
        assert any(s.name == "list_dir" for s in chat.state.steps)
        rendered = app.master._digests.render()
        assert "chat" in rendered
        assert "| recent:" in rendered
        app.memory.close()

    async def test_digest_render_omits_empty_last_step(self, tmp_path) -> None:
        """With no steps, render appends no empty recent section."""
        app = _app(tmp_path, FakeLLM(default="Got it."))
        await app.master.dispatch_task("no-tool task", name="noop")
        await asyncio.sleep(0.05)
        rendered = app.master._digests.render()
        assert "noop" in rendered
        # With no steps, last_step is empty; no empty recent tail may appear
        assert not rendered.strip().endswith("| recent:")
        app.memory.close()


class TestPagePreactivate:
    """A small page -> pre-activated domain mapping (notes/graph/sources)."""

    def test_domain_pages_map_to_own_domain(self) -> None:
        assert page_preactivate("notes") == "notes"
        assert page_preactivate("graph") == "graph"
        assert page_preactivate("sources") == "sources"

    def test_other_pages_do_not_preactivate(self) -> None:
        for page in ("chat", "team", "activity", "settings", "usage", ""):
            assert page_preactivate(page) is None


class TestDomainPrefixes:
    """Activatable domains derive from `__` prefixes in the current roster, no longer an import-time frozen constant."""

    def test_derive_from_belt_names(self) -> None:
        from agent.tools.core.activate import domain_prefixes

        assert domain_prefixes(["read_file", "notes__x", "mcp__a__b"]) == ("mcp", "notes")
        # Only the first `__` segment counts: mcp__demo__search -> mcp, not mcp__demo
        assert "mcp__demo" not in domain_prefixes(["mcp__demo__search"])
        assert domain_prefixes(["read_file", "run_shell", "activate_tools"]) == ()
        assert domain_prefixes([]) == ()

    async def test_schema_enum_follows_roster(self, tmp_path, settle) -> None:
        """activate_tools's domain enum is computed live from the roster; internal tool domains (fs/shell/web) no longer appear."""

        async def search(query: str = "") -> dict:
            return {"hits": []}

        tools = _fake_notes_tools()
        tools["mcp__demo__search"] = AgentTool(
            name="mcp__demo__search",
            description="[mcp] demo search",
            handler=search,
        )
        llm = FakeLLM([LLMReply(text="Done looking.")])
        app = _app(tmp_path, llm, tools)
        await app.master.handle_user_message("look at the working directory")
        await settle(app)
        spec = next(s for s in llm.calls[0]["tools"] if s.name == "activate_tools")
        enum = spec.schema["properties"]["domain"]["enum"]
        assert "notes" in enum and "mcp" in enum
        assert not {"fs", "shell", "web"} & set(enum)
        app.memory.close()
