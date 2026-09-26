"""Tests for the deterministic compressor: budget-keeping truncation of old
tool results, pair-atomic pruning, and the span-width accounting the editor
and snapshot paths share."""

from typing import Any

from agent.context import compress, estimate_tokens
from agent.context.compressor import _prune_span


class TestCompressor:
    def test_under_budget_untouched(self) -> None:
        msgs = [{"role": "user", "content": "short"}]
        assert compress(msgs, budget=100) == msgs

    def test_tool_results_compressed_system_kept(self) -> None:
        msgs = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "task"},
            {"role": "tool", "content": "very long tool result " * 200},
            {"role": "assistant", "content": "ok"},
            {"role": "user", "content": "continue"},
            {"role": "assistant", "content": "working"},
            {"role": "user", "content": "check again"},
            {"role": "assistant", "content": "right away"},
        ]
        out = compress(msgs, budget=100)
        assert out[0]["role"] == "system" and out[0]["content"] == "system prompt"
        assert estimate_tokens(out) < estimate_tokens(msgs)
        assert any(
            "已压缩" in str(m.get("content", "")) for m in out
        )  # oldest tool result truncated

    def test_all_system_overflow_terminates(self) -> None:
        """Extreme case: over budget with no prunable non-system messages; must return normally, not loop forever."""
        msgs = [{"role": "system", "content": "very long system prompt " * 500} for _ in range(9)]
        out = compress(msgs, budget=100)
        assert len(out) == 9  # system is never compressed, but the loop must terminate

    def test_prune_false_truncates_without_dropping(self) -> None:
        """prune=False only truncates, never drops entries: on a same-turn transcript an
        assistant(tool_calls) and its tool rows must not be split, or the endpoint returns 400."""
        msgs: list[dict[str, Any]] = [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "task"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "a"}]},
            {"role": "tool", "tool_call_id": "a", "content": "old result " * 300},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "b"}]},
            {"role": "tool", "tool_call_id": "b", "content": "new result " * 300},
            {"role": "user", "content": "continue"},
            {"role": "assistant", "content": "wrap up"},
            {"role": "user", "content": "continue again"},
        ]
        out = compress(msgs, budget=200, prune=False)
        assert len(out) == len(msgs)  # truncate only, message count unchanged
        assert "已压缩" in out[3]["content"]  # old tool row truncated (outside the last 4)
        assert out[5]["content"] == "new result " * 300  # untouched within the most recent 4
        assert out[0]["content"] == "system prompt"  # system preserved

    @staticmethod
    def _tool_pair_msgs() -> list[dict]:
        """A valid transcript of several user -> assistant(tool_calls) -> tool rounds (over budget)."""

        def long(text: str) -> str:
            return text * 20

        return [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": long("round-1 task")},
            {"role": "assistant", "content": long("call a tool"), "tool_calls": [{"id": "a1"}]},
            {"role": "tool", "tool_call_id": "a1", "content": long("first result set")},
            {"role": "assistant", "content": long("round-1 summary")},
            {"role": "user", "content": long("round-2 task")},
            {
                "role": "assistant",
                "content": long("call two tools in parallel"),
                "tool_calls": [{"id": "b1"}, {"id": "b2"}],
            },
            {"role": "tool", "tool_call_id": "b1", "content": long("second result set one")},
            {"role": "tool", "tool_call_id": "b2", "content": long("second result set two")},
            {"role": "user", "content": long("round-3 task")},
            {"role": "assistant", "content": "final reply"},
        ]

    @staticmethod
    def _pairs_intact(msgs: list[dict]) -> bool:
        """Checks pairing shape: each assistant with tool_calls is followed by tool rows matching in
        count and ids; a tool row is preceded by either its assistant or a same-group tool row."""
        for idx, m in enumerate(msgs):
            role = m.get("role")
            if role == "tool":
                prev = msgs[idx - 1] if idx else None
                ok = prev is not None and (
                    (prev.get("role") == "assistant" and prev.get("tool_calls"))
                    or prev.get("role") == "tool"
                )
                if not ok:
                    return False
            if role == "assistant" and m.get("tool_calls"):
                ids = [c["id"] for c in m["tool_calls"]]
                k = 0
                while idx + 1 + k < len(msgs) and msgs[idx + 1 + k].get("role") == "tool":
                    k += 1
                got = [msgs[idx + 1 + j].get("tool_call_id") for j in range(k)]
                if k != len(ids) or got != ids:
                    return False
        return True

    def test_prune_true_drops_tool_pairs_atomically(self) -> None:
        """prune=True drops whole groups: any assistant carrying tool_calls keeps all its tool rows,
        and no orphan tool rows may appear."""
        msgs = self._tool_pair_msgs()
        out = compress(msgs, budget=200, prune=True)
        assert len(out) < len(msgs)  # pruning actually happened
        assert self._pairs_intact(out)
        ids_left = {m.get("tool_call_id") for m in out if m.get("role") == "tool"}
        calls_left = {
            c["id"] for m in out if m.get("role") == "assistant" for c in m.get("tool_calls", [])
        }
        assert ids_left == calls_left  # neither side of a pair is missing
        assert "a1" not in ids_left  # the oldest tool pair is dropped as a whole

    def test_prune_true_keeps_recent_tail(self) -> None:
        """Prune down to len(out) <= 8: the most recent rounds (including the last tool pair) are kept verbatim."""
        msgs = self._tool_pair_msgs()
        out = compress(msgs, budget=200, prune=True)
        assert len(out) <= 8
        assert out[-1]["content"] == "final reply"  # final round still present
        assert "round-3 task" in out[-2]["content"]
        last_pair = next(m for m in reversed(out) if m.get("tool_calls"))
        idx = out.index(last_pair)
        assert [c["id"] for c in last_pair["tool_calls"]] == ["b1", "b2"]  # newest pair complete
        assert [out[idx + 1]["tool_call_id"], out[idx + 2]["tool_call_id"]] == ["b1", "b2"]

    def test_prune_span_group_widths(self) -> None:
        """The helper's span width is >1 iff an assistant+tools group is removed."""
        msgs: list[dict[str, Any]] = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "u"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "t"}]},
            {"role": "tool", "tool_call_id": "t", "content": "r"},
            {"role": "assistant", "content": "plain"},
            {"role": "tool", "tool_call_id": "x", "content": "orphan"},
        ]
        assert _prune_span(msgs, 0) == (1, 2)  # skip system, drop the lone user
        assert _prune_span(msgs, 2) == (2, 4)  # assistant + tool as one group
        assert _prune_span(msgs, 4) == (4, 5)  # assistant without tool_calls dropped alone
        assert _prune_span(msgs, 5) == (5, 6)  # leading orphan tool dropped alone
        assert _prune_span(msgs, 6) == (6, 6)  # out of range: nothing to prune
