"""Capability registry for the notes service (assembly entry point).

Capabilities are registered into the shared registry from per-concern
modules imported below. Human users and agents consume the same
capabilities. Public symbols: Deps / init_deps / registry.
"""

from __future__ import annotations

from . import batch as _batch  # noqa: F401
from . import catalog as _catalog  # noqa: F401
from . import history as _history  # noqa: F401
from . import lifecycle as _lifecycle  # noqa: F401
from . import transfer as _transfer  # noqa: F401
from . import view as _view  # noqa: F401
from .runtime import Deps, init_deps, registry

__all__ = ["Deps", "init_deps", "registry"]
