"""Price table matching and read-side cost conversion (D-06): longest prefix
wins, unpriced models report no cost."""

from __future__ import annotations

from llm.pricing import cost_usd, resolve_price


class _Settings:
    def __init__(self, table) -> None:
        self.table = table

    def get(self, key: str):
        return self.table if key == "llm.pricing" else None


TABLE = {
    "gpt-4o": {"input": 2.5, "output": 10.0},
    "gpt-4o-mini": {"input": 0.15, "output": 0.6},
    "deepseek": {"input": 0.27, "output": 1.1},
}


class TestResolvePrice:
    def test_exact_beats_prefix(self) -> None:
        assert resolve_price("gpt-4o-mini", TABLE) == (0.15 / 1e6, 0.6 / 1e6)
        assert resolve_price("gpt-4o-2024-08-06", TABLE) == (2.5 / 1e6, 10.0 / 1e6)

    def test_unpriced_is_none(self) -> None:
        assert resolve_price("claude-x", TABLE) is None
        assert resolve_price("", TABLE) is None
        assert resolve_price("gpt-4o", {}) is None
        assert resolve_price("gpt-4o", {"bad": {}}) is None  # half-specified entry ignored


class TestCost:
    def test_cost_is_read_side_and_precise(self) -> None:
        cost = cost_usd("gpt-4o-mini", 1_000_000, 500_000, TABLE)
        assert cost == round(0.15 + 0.3, 6)
        assert cost_usd("unknown", 10**9, 0, TABLE) is None

    def test_catch_all_entry_serves_totals(self) -> None:
        assert cost_usd("*", 1_000_000, 0, {"*": {"input": 1.0, "output": 2.0}}) == 1.0
