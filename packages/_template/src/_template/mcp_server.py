"""Expose the registry as an MCP server over stdio; agents and
external clients consume this service's capabilities through it.

Run from the repo root with: python -m _template.mcp_server
(requires pip install 'mcp>=1.0'; for stdio wiring details, refer to the
documentation of the MCP SDK version in use).
"""

from __future__ import annotations


def main():
    """Build and return the MCP server; wiring is shared with the REST entry
    point via wiring.py."""
    import tempfile
    from pathlib import Path

    from platform_capability import build_server

    from .wiring import wire

    w = wire(Path(tempfile.gettempdir()) / "template-mcp")
    return build_server(w.registry, name="template")


if __name__ == "__main__":
    main()
