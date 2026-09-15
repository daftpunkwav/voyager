"""Tests for the in-harness lightweight run_snippet tool."""

from __future__ import annotations

from pathlib import Path

import pytest
from agent.llm import ToolCall
from agent.policy import PolicyEngine
from agent.tools.core.base import Toolbelt
from agent.tools.workspace.run_snippet import run_snippet_tool


@pytest.fixture()
def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "workspace"
    ws.mkdir(parents=True, exist_ok=True)
    return ws


class TestRunSnippet:
    async def test_successful_python_execution(self, workspace: Path) -> None:
        tool = run_snippet_tool(workspace)
        result = await tool.handler(code="print('Hello, Python!')", language="python")
        assert "exit=0" in result
        assert "Hello, Python!" in result

    async def test_successful_javascript_execution(self, workspace: Path) -> None:
        tool = run_snippet_tool(workspace)
        result = await tool.handler(
            code="const a = 10; const b = 20; console.log(`sum=${a + b}`);",
            language="javascript",
        )
        assert "exit=0" in result
        assert "sum=30" in result

    async def test_successful_typescript_execution(self, workspace: Path) -> None:
        tool = run_snippet_tool(workspace)
        code = (
            "interface Point { x: number; y: number }\n"
            "const p: Point = { x: 3, y: 7 };\n"
            "console.log(`point: ${p.x},${p.y}`);\n"
        )
        result = await tool.handler(code=code, language="typescript")
        assert "exit=0" in result
        assert "point: 3,7" in result

    async def test_empty_code_skipped(self, workspace: Path) -> None:
        tool = run_snippet_tool(workspace)
        result = await tool.handler(code="   ")
        assert "[执行跳过]" in result

    async def test_unsupported_language(self, workspace: Path) -> None:
        tool = run_snippet_tool(workspace)
        result = await tool.handler(code="puts 'hi'", language="ruby")
        assert "[暂不支持]" in result

    async def test_destructive_command_blocked(self, workspace: Path) -> None:
        tool = run_snippet_tool(workspace)
        result = await tool.handler(code="import os; os.system('rm -rf /')")
        assert "[安全拒绝]" in result

    async def test_pedagogical_error_zerodivision_python(self, workspace: Path) -> None:
        tool = run_snippet_tool(workspace)
        result = await tool.handler(code="x = 10 / 0", language="python")
        assert "exit=" in result
        assert "ZeroDivisionError" in result
        assert "[教学诊断]" in result
        assert "除零错误" in result

    async def test_pedagogical_error_indexerror_python(self, workspace: Path) -> None:
        tool = run_snippet_tool(workspace)
        result = await tool.handler(code="items = [1, 2]; print(items[5])", language="python")
        assert "exit=" in result
        assert "IndexError" in result
        assert "[教学诊断]" in result
        assert "索引越界" in result

    async def test_pedagogical_error_referenceerror_js(self, workspace: Path) -> None:
        tool = run_snippet_tool(workspace)
        result = await tool.handler(code="console.log(undefinedVariable);", language="javascript")
        assert "exit=" in result
        assert "ReferenceError" in result
        assert "[教学诊断]" in result
        assert "引用错误" in result

    async def test_timeout_interruption(self, workspace: Path) -> None:
        tool = run_snippet_tool(workspace)
        result = await tool.handler(code="import time; time.sleep(10)", timeout=1)
        assert "[超时]" in result

    async def test_image_artifact_detection(self, workspace: Path) -> None:
        tool = run_snippet_tool(workspace)
        code = "with open('chart.png', 'wb') as f: f.write(b'fake_png_data')"
        result = await tool.handler(code=code)
        assert "exit=0" in result
        assert "[生成图表]" in result
        assert "sandbox/snippets/chart.png" in result


class TestPolicyGate:
    """Code execution inherits the shell-dimension gate (L2 by default):
    without a confirm channel the call is skipped, never run silently."""

    async def test_requires_confirmation_by_default(self, workspace: Path) -> None:
        tool = run_snippet_tool(workspace)
        belt = Toolbelt({tool.name: tool}, PolicyEngine())
        out = await belt.call_detailed(ToolCall("1", "run_snippet", {"code": "print('hi')"}))
        assert out.ok is False
        assert "[需确认]" in out.text

    async def test_executes_after_confirmation(self, workspace: Path) -> None:
        async def _allow(_prompt: str) -> bool:
            return True

        tool = run_snippet_tool(workspace)
        belt = Toolbelt({tool.name: tool}, PolicyEngine(), confirm=_allow)
        out = await belt.call_detailed(ToolCall("1", "run_snippet", {"code": "print('hi')"}))
        assert out.ok is True
        assert "hi" in out.text
