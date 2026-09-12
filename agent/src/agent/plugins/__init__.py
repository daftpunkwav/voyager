"""Plugin package (bundle / per-item): discovery, approval, declarative
skill/hook loading.
"""

from agent.plugins.manager import APPROVALS_KEY, APPROVED_KEY, PluginManager
from agent.plugins.manifest import PluginManifest, discover, load_manifest

__all__ = [
    "APPROVALS_KEY",
    "APPROVED_KEY",
    "PluginManager",
    "PluginManifest",
    "discover",
    "load_manifest",
]
