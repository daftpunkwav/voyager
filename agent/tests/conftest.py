"""Shared test fixtures for agent tests.

The assembled-app assertion helpers (formerly tests/helpers.py) are exposed
as fixtures so test modules never need to import the test tree as a package.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

import pytest
from agent.main import AgentApp
from platform_contracts import DomainEvent


def _agent_replies(app: AgentApp) -> list[str]:
    """Contents of agent.message events from the event log, in ascending seq order."""
    return [e.payload["content"] for _, e in app.log.read_after(types=[DomainEvent.AGENT_MESSAGE])]


async def _settle(app: AgentApp) -> None:
    """Wait for all background turn tasks spawned by handle_user_message to finish.

    The entry point returns as soon as the asyncio.Task is created; drain the
    background turns before asserting on llm.calls or events.
    """
    while app.master._bg:
        await asyncio.gather(*list(app.master._bg))


@pytest.fixture()
def agent_replies():
    """Callable: agent_replies(app) -> list[str]."""
    return _agent_replies


@pytest.fixture()
def settle():
    """Callable: await settle(app) to drain background turns."""
    return _settle


async def _wait_until(predicate: Callable[[], bool], *, timeout: float = 3.0) -> None:
    """Poll predicate every 10ms until true or timeout (the caller asserts afterwards)."""
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        await asyncio.sleep(0.01)


@pytest.fixture()
def wait_until():
    """Callable: await wait_until(lambda: cond) for load-independent eventual assertions."""
    return _wait_until
