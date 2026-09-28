"""Host adapter layer for the browser service.

Responsibilities:
- Accept browser commands and return a uniform BrowserResult
- Enforce the domain allowlist on navigate (FORBIDDEN otherwise)

The real browser runs in desktop/browser-host; this service only dispatches
commands and collects results. The IPC channel to that host is not wired yet,
so every command is refused with BROWSER.UNAVAILABLE instead of reporting a
fabricated success: a caller (the agent tool pipeline, a REST consumer) must
never see ok=True with placeholder content. The adapter signature stays the
target shape for the real implementation, so wiring IPC later changes only
these five functions.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from platform_contracts import ErrorSuffix, ServiceError

#: Uniform refusal while desktop/browser-host IPC is not wired. Kept as a
#: module constant so the eventual real implementation can raise the same
#: shape on a dead channel.
_NOT_WIRED = "browser host integration is not wired yet (desktop/browser-host IPC pending)"


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
    raise ServiceError("browser", ErrorSuffix.UNAVAILABLE, _NOT_WIRED)


async def click(session_id: str, selector: str, *, allowed_domains: list[str]) -> BrowserResult:
    """Click an element."""
    raise ServiceError("browser", ErrorSuffix.UNAVAILABLE, _NOT_WIRED)


async def type_text(
    session_id: str, selector: str, text: str, *, allowed_domains: list[str]
) -> BrowserResult:
    """Type text into an element."""
    raise ServiceError("browser", ErrorSuffix.UNAVAILABLE, _NOT_WIRED)


async def read_page(session_id: str, *, allowed_domains: list[str]) -> BrowserResult:
    """Read the current page text."""
    raise ServiceError("browser", ErrorSuffix.UNAVAILABLE, _NOT_WIRED)


async def screenshot(
    session_id: str, *, allowed_domains: list[str], workspace_dir: str
) -> BrowserResult:
    """Take a screenshot and save it under workspace/browser-screenshots/."""
    raise ServiceError("browser", ErrorSuffix.UNAVAILABLE, _NOT_WIRED)


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
