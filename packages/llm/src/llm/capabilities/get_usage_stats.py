"""get_usage_stats capability: usage statistics grouped by model for the
usage page, with cost converted on the read side (D-06) when the llm.pricing
price table covers a model; unpriced models carry no cost field (nothing is
invented). Row shape: input/output token keys as produced by the store."""

from __future__ import annotations

from typing import Any

from platform_capability import capability

from llm.capabilities.common import registry, require_deps
from llm.pricing import PRICING_KEY, cost_usd


def _tokens(row: dict[str, Any]) -> tuple[int, int]:
    return int(row.get("input") or 0), int(row.get("output") or 0)


def _apply_costs(stats: dict) -> dict:
    """Attach cost_usd to the rows the price table covers: totals (only when
    a '*' catch-all entry exists — totals mix models), by_model, and each
    by_day row's per-model breakdown."""
    deps = require_deps()
    table = deps.settings.get(PRICING_KEY) if deps.settings is not None else None
    if not isinstance(table, dict) or not table:
        return stats
    totals = stats.get("totals")
    if isinstance(totals, dict) and isinstance(table.get("*"), dict):
        inp, outp = _tokens(totals)
        cost = cost_usd("*", inp, outp, {"*": table["*"]})
        if cost is not None:
            totals["cost_usd"] = cost
    for row in stats.get("by_model") or []:
        if not isinstance(row, dict) or not row.get("model"):
            continue
        inp, outp = _tokens(row)
        cost = cost_usd(str(row["model"]), inp, outp, table)
        if cost is not None:
            row["cost_usd"] = cost
    for day in stats.get("by_day") or []:
        if not isinstance(day, dict):
            continue
        day_cost = 0.0
        priced = False
        for model_row in day.get("by_model") or []:
            if not isinstance(model_row, dict) or not model_row.get("model"):
                continue
            inp, outp = _tokens(model_row)
            cost = cost_usd(str(model_row["model"]), inp, outp, table)
            if cost is not None:
                day_cost += cost
                priced = True
        if priced:
            day["cost_usd"] = round(day_cost, 6)
    return stats


@capability(
    registry,
    name="get_usage_stats",
    description="Usage statistics (last N days, grouped by model; source for the usage page)",
)
def get_usage_stats(days: int = 30) -> dict:
    return _apply_costs(require_deps().store.usage_stats(days))
