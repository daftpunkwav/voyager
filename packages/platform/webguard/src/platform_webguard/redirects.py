"""Per-hop redirect guard: the chain is never followed automatically — each
hop is rewritten by the caller and re-checked against policy + DNS before
the next request, so a whitelisted domain cannot 302 its way to an intranet
or cloud-metadata target. Pure helpers only; the loop lives with the caller
(the policy engine is the caller's vocabulary).
"""

from __future__ import annotations

import httpx

#: Hop budget for the agent's web tools (each hop is fully re-validated, so
#: the budget bounds total work, not trust). The sources importer runs its
#: own, smaller budget.
MAX_REDIRECTS = 5


def redirect_target(base_url: str, response: httpx.Response) -> str | None:
    """Absolute next URL when the response is a redirect with a location,
    else None (callers then treat the response as final)."""
    if not (response.is_redirect and response.has_redirect_location):
        return None
    location = response.headers.get("location", "")
    return str(httpx.URL(base_url).join(location))


__all__ = ["MAX_REDIRECTS", "redirect_target"]
