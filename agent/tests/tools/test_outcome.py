"""Tests for the tool-call outcome envelope and argument validation:
normalize() preserves the legacy LLM-facing text, validate_arguments()
rejects malformed calls before any side effect, and call_detailed()
exposes the same pipeline as call() with structured metadata.
"""

from agent.llm import ToolCall
from agent.policy import FsPolicy, PolicyEngine
from agent.tools import AgentTool, Toolbelt, ensure_workdir, fs_tools
from agent.tools.core.invoke import validate_arguments
from agent.tools.core.outcome import ToolResult, normalize


def _belt(root, **kw) -> Toolbelt:
    return Toolbelt(
        fs_tools([root]),
        PolicyEngine(fs=FsPolicy(roots=(str(root),))),
        **kw,
    )


class TestNormalize:
    def test_str_passes_through(self) -> None:
        out = normalize("read", "hello")
        assert (out.name, out.ok, out.text, out.title) == ("read", True, "hello", "read")
        assert out.metadata == {}

    def test_dict_serializes_like_legacy(self) -> None:
        out = normalize("write", {"written": "a", "chars": 3})
        assert out.ok is True
        assert out.text == '{"written": "a", "chars": 3}'

    def test_tool_result_defaults_empty_title(self) -> None:
        out = normalize("grep", ToolResult(name="grep", ok=True, text="m", metadata={"total": 1}))
        assert out.title == "grep"
        assert out.metadata == {"total": 1}

    def test_none_metadata_defended(self) -> None:
        """A hand-built outcome with metadata=None must not crash the
        pipeline with TypeError."""
        out = normalize("x", ToolResult(name="x", ok=False, text="t", metadata=None))  # type: ignore[arg-type]  # None must be defended
        assert out.metadata == {}
        assert ToolResult(name="x", ok=True, text="t", metadata=None).with_title("T")  # type: ignore[arg-type]  # None must be defended.metadata == {}

    def test_with_title_falls_back_to_name(self) -> None:
        out = ToolResult(name="glob", ok=True, text="f").with_title("")
        assert out.title == "glob"


class TestValidateArguments:
    def _tool(self) -> AgentTool:
        return AgentTool(
            name="edit",
            description="edit",
            handler=lambda **kw: "ok",
            schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old_text": {"type": "string"},
                    "new_text": {"type": "string"},
                    "count": {"type": "integer"},
                },
                "required": ["path", "old_text", "new_text"],
            },
        )

    def test_valid_call_passes(self) -> None:
        assert (
            validate_arguments(self._tool(), {"path": "a", "old_text": "x", "new_text": "y"})
            is None
        )

    def test_unknown_keys_ignored(self) -> None:
        assert (
            validate_arguments(
                self._tool(),
                {"path": "a", "old_text": "x", "new_text": "y", "extra": 1},
            )
            is None
        )

    def test_missing_required_names_them(self) -> None:
        err = validate_arguments(self._tool(), {"path": "a"})
        assert err is not None and err.startswith("[参数错误]")
        assert "old_text" in err and "new_text" in err

    def test_null_required_counts_as_missing(self) -> None:
        err = validate_arguments(self._tool(), {"path": "a", "old_text": None, "new_text": "y"})
        assert err is not None and "old_text" in err

    def test_null_optional_skipped(self) -> None:
        assert (
            validate_arguments(
                self._tool(),
                {"path": "a", "old_text": "x", "new_text": "y", "count": None},
            )
            is None
        )

    def test_wrong_type_guided(self) -> None:
        err = validate_arguments(
            self._tool(),
            {"path": "a", "old_text": "x", "new_text": "y", "count": "two"},
        )
        assert err is not None and "count" in err and "integer" in err

    def test_bool_is_not_integer(self) -> None:
        err = validate_arguments(
            self._tool(),
            {"path": "a", "old_text": "x", "new_text": "y", "count": True},
        )
        assert err is not None and "integer" in err

    def test_non_dict_rejected(self) -> None:
        err = validate_arguments(self._tool(), ["path"])
        assert err is not None and err.startswith("[参数错误]")

    def test_empty_schema_passes_anything(self) -> None:
        tool = AgentTool(name="x", description="x", handler=lambda: "ok")
        assert validate_arguments(tool, {"anything": 1}) is None


class TestDetailedPipeline:
    async def test_invalid_args_never_reach_handler_or_confirm(self, tmp_path) -> None:
        root = ensure_workdir(tmp_path / "ws")
        seen: list[str] = []

        async def spy_confirm(prompt: str) -> bool:
            seen.append(prompt)
            return True

        belt = _belt(root, confirm=spy_confirm)
        out = await belt.call_detailed(ToolCall("1", "read", {"path": 42}))
        assert out.ok is False
        assert out.text.startswith("[参数错误]")
        assert seen == []  # no confirmation raised for a malformed call

    async def test_detailed_matches_call_text(self, tmp_path) -> None:
        root = ensure_workdir(tmp_path / "ws")
        (root / "repo" / "a.txt").write_text("hello\n", encoding="utf-8")
        belt = _belt(root)
        call = ToolCall("1", "read", {"path": "repo/a.txt"})
        assert (await belt.call_detailed(call)).text == await belt.call(call)

    async def test_unknown_tool_outcome(self, tmp_path) -> None:
        root = ensure_workdir(tmp_path / "ws")
        out = await _belt(root).call_detailed(ToolCall("1", "nope", {}))
        assert out.ok is False and out.text.startswith("[未知工具]")

    async def test_spill_marks_truncated_metadata(self, tmp_path) -> None:
        root = ensure_workdir(tmp_path / "ws")
        (root / "repo" / "big.txt").write_text("z" * 300, encoding="utf-8")
        belt = Toolbelt(
            fs_tools([root]),
            PolicyEngine(fs=FsPolicy(roots=(str(root),))),
            result_budget=lambda text, _name: text if len(text) <= 10 else text[:10] + "…[spilled]",
        )
        out = await belt.call_detailed(ToolCall("1", "read", {"path": "repo/big.txt"}))
        assert out.ok is True
        assert out.metadata.get("truncated") is True
        assert out.text.endswith("…[spilled]")
