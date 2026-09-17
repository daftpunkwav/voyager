"""LLM capability registry package: one capability per file, registered
into the shared Registry("llm") on import.

Public entry points (unchanged for host wiring and tests):
    from llm.capabilities import Deps, init_deps, registry
"""

from __future__ import annotations

from llm.capabilities import (  # noqa: F401  # registration side effects
    add_provider,
    complete,
    complete_stream,
    embed,
    get_provider_defaults,
    get_usage_stats,
    list_builtin_providers,
    list_models,
    list_providers,
    list_remote_models,
    remove_provider,
    set_api_key,
    test_connection,
    update_provider,
)
from llm.capabilities.common import Deps, init_deps, registry

__all__ = ["Deps", "init_deps", "registry"]
