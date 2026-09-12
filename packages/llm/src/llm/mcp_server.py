"""Registry -> MCP server (stdio). Agents / external clients consume
llm capabilities through it.

Run: python -m llm.mcp_server (from the repo root; requires
pip install 'mcp>=1.0')
"""

from __future__ import annotations


def main():
    import tempfile
    from pathlib import Path

    from platform_capability import build_server

    from .wiring import wire

    w = wire(Path(tempfile.gettempdir()) / "llm-mcp")
    return build_server(w.registry, name="llm")


if __name__ == "__main__":
    main()
