"""Python fallback engine.

Pure Python (ast/regex), no external dependencies; uniform `call(name, args)`
dispatch. No global engine singleton: each assembly point constructs its own
instance, so tests never leak state between each other.
"""

from .engine import GraphEngine

__all__ = ["GraphEngine"]
