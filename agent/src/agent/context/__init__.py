"""Context engineering: assembly, usage accounting, compression, page
awareness, and on-demand loading.
"""

from agent.context.builder import ContextBuilder
from agent.context.compressor import compress, estimate_tokens
from agent.context.loader import OnDemandLoader
from agent.context.pages import PageContextRegistry, PageSummary
from agent.context.usage import (
    UsageTracker,
    over_threshold,
    render_status_line,
    usage_status,
)
from agent.runtime.tokens import ContextWindow, resolve_window

__all__ = [
    "ContextBuilder",
    "ContextWindow",
    "OnDemandLoader",
    "PageContextRegistry",
    "PageSummary",
    "UsageTracker",
    "compress",
    "estimate_tokens",
    "over_threshold",
    "render_status_line",
    "resolve_window",
    "usage_status",
]
