"""Tests for the Toolbelt assembly surface: capability trimming, the residual
write_roots confirm flow, L1 notify wiring, and the app-dimension target rule."""

from agent.llm import ToolCall
from agent.policy import FsPolicy, PolicyEngine
from agent.tools import Toolbelt, fs_tools


def _belt(root, *, confirm=None, notify=None) -> Toolbelt:
    return Toolbelt(
        fs_tools([root]),
        PolicyEngine(fs=FsPolicy(roots=(str(root),))),
        confirm=confirm,
        notify=notify,
    )


async def _yes() -> bool:
    return True


class TestTrim:
    def test_trimmed_removes_write(self, workdir) -> None:
        """Trimming away write means it is truly gone."""
        belt = _belt(workdir).trimmed(["read"])
        assert belt.names() == ["read"]
        assert belt._policy is not None  # trimming keeps the policy engine

    async def test_trimmed_call_blocked(self, workdir) -> None:
        belt = _belt(workdir).trimmed(["read"])
        out = await belt.call(ToolCall("1", "write", {"path": "a", "content": "b"}))
        assert "[未知工具]" in out

    async def test_unknown_tool_suggests_closest_names(self, workdir) -> None:
        """A typo'd or ungranted name gets the roster's nearest matches, so
        the model can self-correct in one call."""
        belt = _belt(workdir)
        out = await belt.call(ToolCall("1", "rea", {"path": "a"}))
        assert "[未知工具]" in out
        assert "read" in out
        # a name with no roster neighbour gets no hint segment
        out = await belt.call(ToolCall("1", "zzzQQQ", {}))
        assert "[未知工具]" in out
        assert "最接近的工具" not in out

    def test_trimmed_prefix_expand_relative_to_belt(self, workdir) -> None:
        """Grants expand against the current roster: explicit names pass, a
        prefix with no roster match invents nothing."""
        belt = _belt(workdir)
        trimmed = belt.trimmed(["read", "edit"])
        assert set(trimmed.names()) == {"read", "edit"}
        # No roster name starts with "note_": the prefix never invents tools
        assert belt.trimmed(["note_*"]).names() == []
        assert not any(n.startswith("notes__") for n in trimmed.names())

    def test_trimmed_bare_star_is_not_prefix(self, workdir) -> None:
        """A bare `*` is not a valid prefix grant (avoiding opening the whole roster in one stroke)."""
        belt = _belt(workdir).trimmed(["*"])
        assert belt.names() == []


class TestConfirmFlow:
    async def test_l2_confirm_approve_and_deny(self, workdir, tmp_path) -> None:
        asked: list[str] = []
        proj = tmp_path / "proj"
        proj.mkdir()

        async def nope(_prompt: str) -> bool:
            asked.append(_prompt)
            return False

        belt = Toolbelt(
            fs_tools([workdir], write_roots=[proj]),
            PolicyEngine(
                fs=FsPolicy(roots=(str(workdir),), write_roots=(str(proj),)),
            ),
            confirm=nope,
        )
        out = await belt.call(ToolCall("1", "write", {"path": str(proj / "f.txt"), "content": "x"}))
        assert "[已取消]" in out and asked  # the confirm prompt really fired
        assert not (proj / "f.txt").exists()  # nothing written

    async def test_l2_without_channel_skipped(self, workdir, tmp_path) -> None:
        proj = tmp_path / "proj"
        proj.mkdir()
        belt = Toolbelt(
            fs_tools([workdir], write_roots=[proj]),
            PolicyEngine(fs=FsPolicy(roots=(str(workdir),), write_roots=(str(proj),))),
        )  # no confirm channel
        out = await belt.call(ToolCall("1", "write", {"path": str(proj / "f.txt"), "content": "x"}))
        assert "[需确认]" in out
        assert not (proj / "f.txt").exists()

    async def test_l1_notify_fired(self, workdir) -> None:
        seen: list[str] = []
        (workdir / "f.txt").write_text("x")

        async def notify(msg: str) -> None:
            seen.append(msg)

        belt = _belt(workdir, notify=notify)
        await belt.call(ToolCall("1", "write", {"path": "g.txt", "content": "y"}))
        assert seen and "write" in seen[0]

    async def test_unknown_tool(self, workdir) -> None:
        out = await _belt(workdir).call(ToolCall("1", "nope", {}))
        assert "[未知工具]" in out


class TestAppPolicyTarget:
    async def test_app_dimension_uses_tool_name_not_url(self) -> None:
        """The app dimension uses the tool name as target; bridge tools carrying a url argument still match by tool name."""
        from agent.llm import ToolCall
        from agent.policy import AppPolicy, PolicyEngine
        from agent.tools import AgentTool, Toolbelt

        async def handler(url: str = "") -> dict:
            return {"ok": True, "url": url}

        tool = AgentTool(
            name="notes__create_note",
            description="写笔记",
            handler=handler,
            schema={"url": {"type": "string"}},
            dimension="app",
            write=True,
        )
        allowed = Toolbelt(
            {"notes__create_note": tool},
            PolicyEngine(app=AppPolicy(allowed=frozenset({"notes__create_note"}))),
        )
        out = await allowed.call(ToolCall("1", "notes__create_note", {"url": "https://evil.com"}))
        assert "ok" in out

        denied = Toolbelt(
            {"notes__create_note": tool},
            PolicyEngine(
                app=AppPolicy(allowed=frozenset({"*"}), denied=frozenset({"notes__create_note"}))
            ),
        )
        out = await denied.call(ToolCall("2", "notes__create_note", {"url": "https://github.com"}))
        assert "[已拒绝]" in out
