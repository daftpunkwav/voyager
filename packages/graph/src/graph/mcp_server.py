"""Expose the graph registry as an MCP server over stdio.

Run with: python -m graph.mcp_server (from the repo root;
requires pip install 'mcp>=1.0').
"""

from __future__ import annotations


def main():
    import tempfile
    from pathlib import Path

    from platform_capability import build_server

    from .wiring import wire

    w = wire(Path(tempfile.gettempdir()) / "graph-mcp")
    return build_server(w.registry, name="graph")


if __name__ == "__main__":
    main()
