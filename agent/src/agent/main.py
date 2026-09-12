"""Process entry point: builds the agent and runs the event loop resident.

Run from the repository root: ``python -m agent.main``. Assembly lives in
agent.build (build_agent) and the product type in agent.app (AgentApp);
both are re-exported here so existing imports keep working.
"""

from __future__ import annotations

import asyncio

from agent.app import AgentApp
from agent.build import build_agent


async def _serve() -> None:
    app = build_agent()
    print("agent runtime started (event loop resident; Ctrl+C to exit)")
    await app.loop.run()


def main() -> None:
    asyncio.run(_serve())


__all__ = ["AgentApp", "build_agent", "main"]


if __name__ == "__main__":
    main()
