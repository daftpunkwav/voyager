"""get_resource_quota capability: today's token usage and the daily quota
limit (read-only).

The agent's get_resource_quota tool binds the same capability.
"""

from __future__ import annotations

from platform_capability import Registry, capability

from agent.capabilities.deps import CapabilityDeps


def register(reg: Registry, deps: CapabilityDeps) -> None:
    @capability(
        reg,
        name="get_resource_quota",
        description="Today's token usage, estimated cost, and the daily quota limit",
    )
    def get_resource_quota() -> dict:
        """Return today's token usage, estimated cost, and the daily quota.

        - tokens_used_today: same semantics as Meter.tokens_used_today; UTC
          calendar day rollover, input+output combined;
        - daily_tokens: hot-read from agent.resource.daily_tokens, 0 = unlimited;
        - cost_usd: estimate from the static price table plus
          agent.pricing.overrides; "unknown" lists models with no price -
          their tokens are NOT counted as zero cost;
        - no percentage/over-quota derivation is computed here; presentation
          choices are left to the frontend.
        """
        limit = int(deps.settings.get("agent.resource.daily_tokens") or 0)
        used = deps.meter.tokens_used_today()
        cost = deps.meter.cost_today()
        return {
            "tokens_used_today": used,
            "daily_tokens": limit,
            "cost_usd": cost["cost_usd"],
            "cost_unknown_models": cost["unknown"],
        }
