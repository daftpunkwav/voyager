"""Tests for context budget assembly: settings hot-read, fallback on
dirty/unset values, and the built-in floor.
"""

from agent.context.budgets import HISTORY_MAX, ContextBudget, budget_from_settings
from agent.context.compressor import COMPRESS_BUDGET


class _Settings:
    def __init__(self, values: dict[str, object] | None = None) -> None:
        self._values = values or {}

    def get(self, key: str) -> object:
        return self._values.get(key)


def test_defaults_when_unconfigured() -> None:
    budget = budget_from_settings(_Settings())
    assert budget == ContextBudget(history_max=HISTORY_MAX, compress_budget=COMPRESS_BUDGET)


def test_valid_overrides_win() -> None:
    budget = budget_from_settings(
        _Settings(
            {
                "agent.context.history_max": 20,
                "agent.context.compress_budget": 12000,
            }
        )
    )
    assert budget.history_max == 20
    assert budget.compress_budget == 12000


def test_dirty_and_nonpositive_fall_back() -> None:
    budget = budget_from_settings(
        _Settings(
            {
                "agent.context.history_max": "not-a-number",
                "agent.context.compress_budget": -1,
            }
        )
    )
    assert budget.history_max == HISTORY_MAX
    assert budget.compress_budget == COMPRESS_BUDGET
