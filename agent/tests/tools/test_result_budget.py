"""Tests for the oversized tool-result budget: spill file creation,
preview text with a readable path, pass-through under the limit, FIFO
directory bounding, and the end-to-end invoke path via result_budget.
"""

from pathlib import Path

from agent.llm import ToolCall
from agent.policy import PolicyEngine
from agent.tools.core.base import AgentTool, Toolbelt
from agent.tools.core.result_budget import (
    bound_spill_dir,
    spill_result,
)


def _spill_dir(tmp_path: Path) -> Path:
    return tmp_path / "spill"


def test_small_result_passes_through(tmp_path) -> None:
    out = spill_result("short", tool="t", spill_dir=_spill_dir(tmp_path), limit=100)
    assert out == "short"


def test_oversized_result_spilled_with_path(tmp_path) -> None:
    big = "x" * 5000
    out = spill_result(big, tool="my__tool", spill_dir=_spill_dir(tmp_path), limit=1000)
    assert out.startswith("x")  # the preview head comes first
    assert "已截断" in out and "read_file" in out
    files = list(_spill_dir(tmp_path).glob("my__tool-*.txt"))
    assert len(files) == 1
    assert files[0].read_text(encoding="utf-8") == big  # full output preserved
    assert str(files[0]) in out  # the model can find the file


def test_bound_spill_dir_fifo(tmp_path) -> None:
    d = _spill_dir(tmp_path)
    d.mkdir()
    for i in range(5):
        p = d / f"t-{i}.txt"
        p.write_text(str(i), encoding="utf-8")
        p.touch()
    removed = bound_spill_dir(d, cap=3)
    assert removed == 2
    remaining = sorted(p.name for p in d.iterdir())
    assert remaining == ["t-2.txt", "t-3.txt", "t-4.txt"]  # oldest dropped first
    assert bound_spill_dir(d / "missing", cap=3) == 0  # absent dir is a no-op


async def test_invoke_applies_result_budget(tmp_path) -> None:
    """End-to-end: a tool returning a huge string comes back truncated with
    the spill path, via the Toolbelt result_budget channel."""
    calls: list[tuple[str, str]] = []

    def _budget(result: str, tool: str) -> str:
        calls.append((tool, str(len(result))))
        if len(result) > 100:
            return spill_result(result, tool=tool, spill_dir=_spill_dir(tmp_path), limit=100)
        return result

    async def big() -> str:
        return "y" * 2000

    belt = Toolbelt(
        {"big": AgentTool(name="big", description="big output", handler=big)},
        PolicyEngine(),
        result_budget=_budget,
    )
    out = await belt.call(ToolCall("1", "big", {}))
    assert calls == [("big", "2000")]
    assert "已截断" in out
    spill_files = list(_spill_dir(tmp_path).glob("big-*.txt"))
    assert len(spill_files) == 1
    assert spill_files[0].read_text(encoding="utf-8") == "y" * 2000
