"""Static model price table behind the cost view: USD per million tokens.

This is a convenience estimate for usage visibility, not a billing source:
published prices drift, so every entry here is an approximation and the
`agent.pricing.overrides` setting (model -> {input, output, cache_read})
wins over the table. Lookup is deliberately fuzzy (substring over
normalized names) because the same model arrives under many provider
prefixes ("openrouter/deepseek/deepseek-chat", "deepseek-chat", ...).

Unknown models are never silently priced at zero: cost_of returns None and
callers must surface them as an explicit unknown bucket.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPrice:
    """USD per million tokens; cache_read applies to the cached share of
    prompt tokens (cache_write exists for Anthropic-style accounting but is
    not reported by the OpenAI-compatible usage channel)."""

    input: float
    output: float
    cache_read: float = 0.0
    cache_write: float = 0.0


#: Approximate published prices (USD / Mtok), last reviewed 2026-09; override
#: via agent.pricing.overrides when authoritative values matter.
_TABLE: dict[str, ModelPrice] = {
    "deepseek-chat": ModelPrice(input=0.27, output=1.10, cache_read=0.07),
    "deepseek-reasoner": ModelPrice(input=0.55, output=2.19, cache_read=0.14),
    "gpt-5": ModelPrice(input=1.25, output=10.0, cache_read=0.125),
    "gpt-5-mini": ModelPrice(input=0.25, output=2.0, cache_read=0.025),
    "gpt-5-nano": ModelPrice(input=0.05, output=0.40, cache_read=0.005),
    "gpt-4.1": ModelPrice(input=2.0, output=8.0, cache_read=0.50),
    "gpt-4.1-mini": ModelPrice(input=0.40, output=1.60, cache_read=0.10),
    "gpt-4o": ModelPrice(input=2.50, output=10.0, cache_read=1.25),
    "gpt-4o-mini": ModelPrice(input=0.15, output=0.60, cache_read=0.075),
    "claude-sonnet-4-5": ModelPrice(input=3.0, output=15.0, cache_read=0.30, cache_write=3.75),
    "claude-haiku-4-5": ModelPrice(input=1.0, output=5.0, cache_read=0.10, cache_write=1.25),
    "claude-opus-4-1": ModelPrice(input=15.0, output=75.0, cache_read=1.50, cache_write=18.75),
    "gemini-2.5-pro": ModelPrice(input=1.25, output=10.0, cache_read=0.31),
    "gemini-2.5-flash": ModelPrice(input=0.30, output=2.50, cache_read=0.075),
    "gemini-3-pro": ModelPrice(input=2.0, output=12.0, cache_read=0.50),
    "glm-4.6": ModelPrice(input=0.60, output=2.20, cache_read=0.11),
    "glm-4.5": ModelPrice(input=0.60, output=2.20, cache_read=0.11),
    "kimi-k2": ModelPrice(input=0.60, output=2.50, cache_read=0.15),
    "qwen3-max": ModelPrice(input=1.20, output=6.0, cache_read=0.20),
    "qwen3-coder": ModelPrice(input=0.45, output=1.80, cache_read=0.09),
}

#: Provider prefixes dropped before matching (longest match wins below, so
#: this is a normalization aid, not the matching mechanism)
_PROVIDERS = (
    "openrouter/",
    "anthropic/",
    "openai/",
    "google/",
    "deepseek/",
    "moonshotai/",
    "zhipuai/",
    "zhipu/",
    "qwen/",
)


def normalize_model(model: str) -> str:
    """Lowercase and strip known provider prefixes down to a comparable name
    ("openrouter/deepseek/DeepSeek-Chat" -> "deepseek-chat"); unknown
    prefixes collapse to the last path segment."""
    name = (model or "").strip().lower()
    while "/" in name:
        head, _, rest = name.partition("/")
        if f"{head}/" in _PROVIDERS:
            name = rest
        else:
            name = rest
            break
    return name


def lookup(model: str, overrides: dict | None = None) -> ModelPrice | None:
    """Price for a model: settings overrides first (exact normalized match,
    or any table-style dict), then the longest table key contained in the
    normalized name; None = unknown model."""
    name = normalize_model(model)
    if not name:
        return None
    if overrides:
        raw = overrides.get(name)
        if isinstance(raw, dict):
            try:
                return ModelPrice(
                    input=float(raw.get("input", 0)),
                    output=float(raw.get("output", 0)),
                    cache_read=float(raw.get("cache_read", 0)),
                    cache_write=float(raw.get("cache_write", 0)),
                )
            except (TypeError, ValueError):
                pass
    if name in _TABLE:
        return _TABLE[name]
    best = [k for k in _TABLE if k in name]
    if not best:
        return None
    return _TABLE[max(best, key=len)]


def cost_of(
    model: str,
    *,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int = 0,
    overrides: dict | None = None,
) -> float | None:
    """USD cost of one usage record; None when the model is unknown. Cached
    prompt tokens are billed at the cache_read rate, the remainder at input."""
    price = lookup(model, overrides)
    if price is None:
        return None
    cached = max(0, min(cached_tokens, input_tokens))
    billable_input = input_tokens - cached
    return (
        billable_input * price.input + cached * price.cache_read + output_tokens * price.output
    ) / 1_000_000


__all__ = ["ModelPrice", "cost_of", "lookup", "normalize_model"]
