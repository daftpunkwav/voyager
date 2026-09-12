"""Cost conversion from token usage to USD, applied on the read side only
(D-06): prices are never persisted with usage rows, so changing a price
never rewrites history and unpriced models report no cost.

The price table lives in the llm.pricing setting, keyed by exact model name
or by prefix (longest prefix wins; model ids carry date suffixes like
"gpt-4o-2024-08-06" under a "gpt-4o" entry). Units are USD per 1M tokens:
{"gpt-4o": {"input": 2.5, "output": 10.0}}. An unset/empty table means costs
are not reported at all — nothing is invented.
"""

from __future__ import annotations

from typing import Any

USD_PER_M = 1_000_000.0

#: Settings key holding the price table (dict; empty = no costs reported)
PRICING_KEY = "llm.pricing"


def resolve_price(model: str, table: dict[str, Any]) -> tuple[float, float] | None:
    """(input_usd_per_token, output_usd_per_token) for a model, or None.

    Longest prefix match first, then exact; entries missing input/output are
    ignored (a half-priced model reports no cost rather than a wrong one).
    """
    if not isinstance(table, dict) or not model:
        return None
    candidates = []
    for key, spec in table.items():
        if not isinstance(key, str) or not isinstance(spec, dict):
            continue
        raw_in, raw_out = spec.get("input"), spec.get("output")
        if raw_in is None or raw_out is None:
            continue
        try:
            inp = float(raw_in)
            out = float(raw_out)
        except (TypeError, ValueError):
            continue
        if model == key:
            return (inp / USD_PER_M, out / USD_PER_M)
        if model.startswith(key) and key:
            candidates.append((len(key), inp, out))
    if candidates:
        _, inp, out = max(candidates, key=lambda c: c[0])
        return (inp / USD_PER_M, out / USD_PER_M)
    return None


def cost_usd(
    model: str, input_tokens: int, output_tokens: int, table: dict[str, Any]
) -> float | None:
    """USD cost of one usage row at today's prices; None when unpriced."""
    price = resolve_price(model, table)
    if price is None:
        return None
    inp, out = price
    return round(input_tokens * inp + output_tokens * out, 6)


__all__ = ["PRICING_KEY", "USD_PER_M", "cost_usd", "resolve_price"]
