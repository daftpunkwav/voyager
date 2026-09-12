"""Registry -> MCP server (stdio). Agents / external clients consume
code-exec capabilities through it.

Run: python -m code_exec.mcp_server (from the repo root; requires
pip install 'mcp>=1.0')
"""

from __future__ import annotations


def main():
    import tempfile
    from pathlib import Path

    from platform_capability import build_server

    from .wiring import wire

    w = wire(
        Path(tempfile.gettempdir()) / "code-exec-mcp",
        workspace=Path(tempfile.gettempdir()) / "code-exec-workspace",
    )
    return build_server(w.registry, name="code-exec")


if __name__ == "__main__":
    main()
