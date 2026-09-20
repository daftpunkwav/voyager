"""Tests for the dispatch completion-notice synthesizer: short results pass
through verbatim, long results get condensed via the LLM, and any synthesis
failure degrades to the capped excerpt without losing the notice."""

from typing import cast

import pytest
from agent.llm import FakeLLM, LLMClient, LLMReply
from agent.master.synthesize import FALLBACK_CHARS, SYNTHESIZE_THRESHOLD, synthesize_result

_LONG = "结论:迁移完成。" + "细节 " * 200  # well over the threshold


async def test_short_result_passes_through() -> None:
    llm = FakeLLM()
    short = "完成了,两处修改。"
    assert await synthesize_result(llm, "t", short) == short
    assert llm.calls == []  # no LLM call spent on short results


async def test_long_result_is_condensed() -> None:
    llm = FakeLLM([LLMReply(text="迁移完成;配置见 /etc/app;遗留:清理旧桶。")])
    out = await synthesize_result(llm, "migrator", _LONG)
    assert out.startswith("迁移完成")
    assert len(llm.calls) == 1
    assert "migrator" in llm.calls[0]["messages"][0]["content"]  # name in the prompt


async def test_degraded_reply_falls_back_to_excerpt() -> None:
    llm = FakeLLM([LLMReply(text="quota", degraded=True)])
    out = await synthesize_result(llm, "t", _LONG)
    assert out == _LONG[:FALLBACK_CHARS] + " …[已截断]"


async def test_llm_failure_falls_back_without_raising() -> None:
    class _Boom:
        async def complete(self, messages, tools=None):
            raise RuntimeError("down")

    out = await synthesize_result(cast(LLMClient, _Boom()), "t", _LONG)
    assert out == _LONG[:FALLBACK_CHARS] + " …[已截断]"


async def test_threshold_boundary_is_verbatim() -> None:
    llm = FakeLLM()
    exact = "x" * SYNTHESIZE_THRESHOLD
    assert await synthesize_result(llm, "t", exact) == exact


@pytest.mark.parametrize("result", [None, ""])
async def test_empty_results_pass_through(result) -> None:
    llm = FakeLLM()
    assert await synthesize_result(llm, "t", result) == ""
    assert llm.calls == []
