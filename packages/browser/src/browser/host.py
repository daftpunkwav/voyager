"""Host adapter layer for the browser service.

Responsibilities:
- Accept browser commands and return a uniform BrowserResult
- Enforce the domain allowlist on navigate (FORBIDDEN otherwise)

The real browser runs in desktop/browser-host; this service only dispatches
commands and collects results. This is currently a skeleton: calls are
recorded and placeholder results are returned, to be replaced with real IPC
once desktop integration is in place.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from platform_contracts import ErrorSuffix, ServiceError


@dataclass
class BrowserResult:
    """Result of executing a browser command."""

    ok: bool
    url: str
    title: str
    text: str
    screenshot_path: str
    error: str


async def navigate(
    session_id: str, url: str, *, headless: bool, allowed_domains: list[str]
) -> BrowserResult:
    """Navigate to a URL."""
    _check_domain(url, allowed_domains)
    return BrowserResult(
        ok=True,
        url=url,
        title="placeholder",
        text="",
        screenshot_path="",
        error="",
    )


async def click(session_id: str, selector: str, *, allowed_domains: list[str]) -> BrowserResult:
    """Click an element."""
    return BrowserResult(
        ok=True,
        url="",
        title="",
        text=f"clicked {selector}",
        screenshot_path="",
        error="",
    )


async def type_text(
    session_id: str, selector: str, text: str, *, allowed_domains: list[str]
) -> BrowserResult:
    """Type text into an element."""
    return BrowserResult(
        ok=True,
        url="",
        title="",
        text=f"typed into {selector}",
        screenshot_path="",
        error="",
    )


async def read_page(session_id: str, *, allowed_domains: list[str]) -> BrowserResult:
    """Read the current page text."""
    return BrowserResult(
        ok=True,
        url="",
        title="placeholder",
        text="page text placeholder",
        screenshot_path="",
        error="",
    )


async def screenshot(
    session_id: str, *, allowed_domains: list[str], workspace_dir: str
) -> BrowserResult:
    """Take a screenshot and save it under workspace/browser-screenshots/."""
    return BrowserResult(
        ok=True,
        url="",
        title="",
        text="",
        screenshot_path=f"{workspace_dir}/browser-screenshots/{session_id}.png",
        error="",
    )


def _check_domain(url: str, allowed_domains: list[str]) -> None:
    if not allowed_domains:
        return
    netloc = urlparse(url).netloc
    if not any(netloc == d or netloc.endswith(f".{d}") for d in allowed_domains):
        raise ServiceError(
            "browser",
            ErrorSuffix.FORBIDDEN,
            f"Domain not in allowlist: {netloc}",
        )
