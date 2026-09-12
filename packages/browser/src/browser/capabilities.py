"""Browser capability registry: navigate / click / type / read /
screenshot.

Responsibilities:
- Expose the five browser commands (navigate / click / type / read /
  screenshot) as capabilities on the service registry
- Track session metadata in the store (touch on every command)
- Pass settings (headless mode, allowed domains) and the workspace directory
  through to the host adapter

The real browser runs in desktop/browser-host; this service only dispatches
commands and collects results. All outbound network access is gated by the
network permission layer.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from platform_capability import Registry, capability
from platform_eventbus import EventBus
from platform_settings import SettingsStore

from .host import click, navigate, read_page, screenshot, type_text
from .settings import DEFS
from .store import BrowserStore

_DOMAIN = "browser"
registry = Registry(_DOMAIN)


@dataclass
class Deps:
    """Runtime dependencies injected at service startup."""

    store: BrowserStore
    settings: SettingsStore
    bus: EventBus | None
    workspace: Path


_deps: Deps | None = None


def init_deps(deps: Deps) -> None:
    global _deps
    _deps = deps


def _require_deps() -> Deps:
    if _deps is None:
        raise RuntimeError("deps not injected: call init_deps() at service entry first")
    return _deps


def _allowed_domains() -> list[str]:
    return _require_deps().settings.get("browser.allowed_domains") or []


def _headless() -> bool:
    return _require_deps().settings.get("browser.headless")


def _session_dir() -> Path:
    deps = _require_deps()
    d = deps.workspace / "browser-sessions"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _result_dict(result) -> dict[str, Any]:
    return {
        "ok": result.ok,
        "url": result.url,
        "title": result.title,
        "text": result.text,
        "screenshot_path": result.screenshot_path,
        "error": result.error,
    }


@capability(
    registry,
    name="navigate",
    description="Navigate to a URL; returns FORBIDDEN when the domain is restricted",
)
async def navigate_url(url: str) -> dict[str, Any]:
    deps = _require_deps()
    sid = uuid.uuid4().hex[:12]
    deps.store.touch(sid, url)
    result = await navigate(sid, url, headless=_headless(), allowed_domains=_allowed_domains())
    return _result_dict(result)


@capability(registry, name="click", description="Click a page element (CSS selector)")
async def click_element(session_id: str, selector: str) -> dict[str, Any]:
    _require_deps().store.touch(session_id)
    result = await click(session_id, selector, allowed_domains=_allowed_domains())
    return _result_dict(result)


@capability(registry, name="type", description="Type text into an element")
async def type_element(session_id: str, selector: str, text: str) -> dict[str, Any]:
    _require_deps().store.touch(session_id)
    result = await type_text(session_id, selector, text, allowed_domains=_allowed_domains())
    return _result_dict(result)


@capability(registry, name="read", description="Read the visible text of the current page")
async def read(session_id: str) -> dict[str, Any]:
    _require_deps().store.touch(session_id)
    result = await read_page(session_id, allowed_domains=_allowed_domains())
    return _result_dict(result)


@capability(registry, name="screenshot", description="Take a screenshot and return the saved path")
async def take_screenshot(session_id: str) -> dict[str, Any]:
    deps = _require_deps()
    deps.store.touch(session_id)
    result = await screenshot(
        session_id, allowed_domains=_allowed_domains(), workspace_dir=str(deps.workspace)
    )
    return _result_dict(result)


__all__ = ["DEFS", "Deps", "init_deps", "registry"]
