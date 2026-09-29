"""Expose the graph registry as an MCP server over stdio.

Run with: python -m graph.mcp_server (from the repo root;
requires pip install 'mcp>=1.0').
"""

from __future__ import annotations


def main():
    from platform_capability import build_server, secure_data_dir

    from .wiring import wire

    w = wire(secure_data_dir("graph-mcp"))
    return build_server(w.registry, name="graph")


if __name__ == "__main__":
    main()
