"""Tests for the task scratchpad tool."""

from __future__ import annotations

from pathlib import Path

import pytest
from agent.tools.plan.scratchpad import scratchpad_tool


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


class TestScratchpad:
    def test_read_empty_scratchpad(self, workspace: Path) -> None:
        tool = scratchpad_tool(workspace)
        result = tool.handler(action="read")
        assert result == "(演草纸当前为空)"

    def test_write_and_read(self, workspace: Path) -> None:
        tool = scratchpad_tool(workspace)
        write_res = tool.handler(action="write", content="步骤 1: 概念引入\n步骤 2: 编写测试")
        assert "[演草纸已更新]" in write_res

        read_res = tool.handler(action="read")
        assert "步骤 1: 概念引入" in read_res
        assert "步骤 2: 编写测试" in read_res

    def test_append_content(self, workspace: Path) -> None:
        tool = scratchpad_tool(workspace)
        tool.handler(action="write", content="初始想法")
        append_res = tool.handler(action="append", content="补充思路")
        assert "[演草纸已追加]" in append_res

        read_res = tool.handler(action="read")
        assert "初始想法" in read_res
        assert "补充思路" in read_res

    def test_append_empty_content(self, workspace: Path) -> None:
        tool = scratchpad_tool(workspace)
        append_res = tool.handler(action="append", content="")
        assert "[演草纸未变动]" in append_res

    def test_clear_scratchpad(self, workspace: Path) -> None:
        tool = scratchpad_tool(workspace)
        tool.handler(action="write", content="临时记录")
        clear_res = tool.handler(action="clear")
        assert "[演草纸已清空]" in clear_res

        read_res = tool.handler(action="read")
        assert read_res == "(演草纸当前为空)"

    def test_invalid_action(self, workspace: Path) -> None:
        tool = scratchpad_tool(workspace)
        res = tool.handler(action="dance")
        assert "[参数错误]" in res
        assert "不支持的 action" in res
