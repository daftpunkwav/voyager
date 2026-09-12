"""Tests for the workspace search tools (grep/glob) and the shared
path jail: match format, caps, filters, binary handling, and jail parity
with the fs tools.
"""

import json

import pytest
from agent.llm import ToolCall
from agent.policy import FsPolicy, PolicyEngine
from agent.tools import Toolbelt, ensure_workdir, fs_tools
from agent.tools.workspace import search_tools
from agent.tools.workspace.jail import Jail


@pytest.fixture()
def workdir(tmp_path):
    root = ensure_workdir(tmp_path / "workspace")
    (root / "repo").mkdir(exist_ok=True)
    return root


def _belt(root, **kw) -> Toolbelt:
    tools = {}
    tools.update(fs_tools([root]))
    tools.update(search_tools([root]))
    return Toolbelt(
        tools,
        PolicyEngine(fs=FsPolicy(roots=(str(root),))),
        **kw,
    )


def _seed(root) -> None:
    (root / "repo" / "a.py").write_text(
        "import os\n\n\ndef main():\n    print('hello')\n", encoding="utf-8"
    )
    (root / "repo" / "b.md").write_text("# Title\n\nhello world\n", encoding="utf-8")
    (root / "repo" / "sub").mkdir(exist_ok=True)
    (root / "repo" / "sub" / "c.py").write_text("hello again\n", encoding="utf-8")
    (root / "repo" / "blob.bin").write_bytes(b"\x00\x01hello\x02\x03")


class TestGrep:
    async def test_match_format(self, workdir) -> None:
        _seed(workdir)
        out = await _belt(workdir).call(ToolCall("1", "grep", {"pattern": "hello"}))
        assert "[命中 3 处" in out
        assert "repo/a.py:5:" in out
        assert "repo/b.md:3:" in out
        assert "repo/sub/c.py:1:" in out
        assert "blob.bin" not in out  # binaries are skipped silently

    async def test_include_filters_filenames(self, workdir) -> None:
        _seed(workdir)
        out = await _belt(workdir).call(
            ToolCall("1", "grep", {"pattern": "hello", "include": "*.py"})
        )
        assert "[命中 2 处" in out
        assert "b.md" not in out

    async def test_single_file_target(self, workdir) -> None:
        _seed(workdir)
        out = await _belt(workdir).call(
            ToolCall("1", "grep", {"pattern": "Title", "path": "repo/b.md"})
        )
        assert "[命中 1 处" in out

    async def test_no_match(self, workdir) -> None:
        _seed(workdir)
        out = await _belt(workdir).call(ToolCall("1", "grep", {"pattern": "zzzqqq"}))
        assert out.startswith("[无匹配]")

    async def test_max_matches_caps_with_note(self, workdir) -> None:
        _seed(workdir)
        out = await _belt(workdir).call(
            ToolCall("1", "grep", {"pattern": "hello", "max_matches": 2})
        )
        assert "仅显示前 2 条" in out

    async def test_invalid_regex_is_argument_error(self, workdir) -> None:
        out = await _belt(workdir).call(ToolCall("1", "grep", {"pattern": "([a"}))
        assert out.startswith("[参数错误]")

    async def test_empty_pattern_is_argument_error(self, workdir) -> None:
        out = await _belt(workdir).call(ToolCall("1", "grep", {"pattern": "  "}))
        assert out.startswith("[参数错误]")

    async def test_missing_pattern_rejected_by_pipeline(self, workdir) -> None:
        out = await _belt(workdir).call(ToolCall("1", "grep", {}))
        assert out.startswith("[参数错误]")

    async def test_missing_path_reports(self, workdir) -> None:
        out = await _belt(workdir).call(
            ToolCall("1", "grep", {"pattern": "x", "path": "repo/nope"})
        )
        assert out.startswith("[失败]")

    async def test_outside_jail_denied_by_policy(self, workdir, tmp_path) -> None:
        out = await _belt(workdir).call(
            ToolCall("1", "grep", {"pattern": "x", "path": str(tmp_path)})
        )
        assert out.startswith("[已拒绝]")

    async def test_hard_cap_reports_honestly(self, workdir) -> None:
        (workdir / "repo" / "many.txt").write_text(
            "".join(f"hit {i}\n" for i in range(250)), encoding="utf-8"
        )
        out = await _belt(workdir).call(
            ToolCall("1", "grep", {"pattern": "hit", "max_matches": 500})
        )
        assert "[命中 200+ 处，仅显示前 200 条" in out

    async def test_long_output_truncates(self, workdir) -> None:
        (workdir / "repo" / "long.txt").write_text(
            "".join(f"hit {'y' * 200}\n" for _ in range(60)), encoding="utf-8"
        )
        out = await _belt(workdir).call(ToolCall("1", "grep", {"pattern": "hit"}))
        assert out.endswith("…[截断] 用更具体的 pattern / include 缩小范围")


class TestGlob:
    async def test_top_level_pattern(self, workdir) -> None:
        _seed(workdir)
        out = await _belt(workdir).call(ToolCall("1", "glob", {"pattern": "*.py", "path": "repo"}))
        assert '"total": 1' in out
        assert "repo/a.py" in out
        assert "sub/c.py" not in out

    async def test_recursive_pattern(self, workdir) -> None:
        _seed(workdir)
        out = await _belt(workdir).call(
            ToolCall("1", "glob", {"pattern": "**/*.py", "path": "repo"})
        )
        assert '"total": 2' in out

    async def test_non_directory_is_argument_error(self, workdir) -> None:
        _seed(workdir)
        out = await _belt(workdir).call(
            ToolCall("1", "glob", {"pattern": "*", "path": "repo/a.py"})
        )
        assert out.startswith("[参数错误]")

    async def test_missing_pattern_rejected_by_pipeline(self, workdir) -> None:
        out = await _belt(workdir).call(ToolCall("1", "glob", {"path": "repo"}))
        assert out.startswith("[参数错误]")

    async def test_entry_cap_marks_truncated(self, workdir) -> None:
        for i in range(205):
            (workdir / "repo" / f"f{i:03d}.txt").write_text("x\n", encoding="utf-8")
        out = await _belt(workdir).call(ToolCall("1", "glob", {"pattern": "*.txt", "path": "repo"}))
        body = json.loads(out)
        assert body["total"] == 205 and body["truncated"] is True
        assert len(body["files"]) == 200


class TestJail:
    def test_resolve_outside_message_preserved(self, workdir) -> None:
        jail = Jail([workdir])
        with pytest.raises(ValueError, match="路径在工作目录之外"):
            jail.resolve("/etc/passwd")

    def test_resolve_relative_anchors_first_root(self, workdir) -> None:
        jail = Jail([workdir])
        assert jail.resolve("repo/a.py") == (workdir / "repo" / "a.py").resolve()

    def test_empty_roots_rejected(self, workdir) -> None:
        with pytest.raises(ValueError):
            Jail([])

    def test_display_relative_inside_absolute_outside(self, workdir, tmp_path) -> None:
        jail = Jail([workdir])
        assert jail.display(workdir / "repo" / "a.py") == "repo/a.py"
        outside = tmp_path / "x.txt"
        assert jail.display(outside) == str(outside)

    def test_contains_inside_and_outside(self, workdir, tmp_path) -> None:
        jail = Jail([workdir])
        assert jail.contains(workdir / "repo" / "a.py") is True
        assert jail.contains(tmp_path / "x.txt") is False
