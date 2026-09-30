"""GitHub API client: metadata / README / search / starred.

All requests go through the single `_request` outlet (easy to mock in
tests and to handle rate limits). Tokens are passed in by callers via
secrets; the client never touches secret storage. Cloning lives in the
worker, not here.
"""

from __future__ import annotations

import base64
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import urlparse

import httpx
from platform_contracts import ErrorSuffix, ServiceError

_API = "https://api.github.com"
_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)
#: Pin the REST API version: without this header GitHub serves the behavior
#: of the current default version, which can shift under us (breaking
#: changes to existing fields ship only in new dated versions). The single
#: constant is the upgrade point.
_API_VERSION = "2022-11-28"

#: Owner/repo names feed the clone destination (workspace/repo/{owner}__{repo})
#: and API paths; anything outside GitHub's charset is rejected up front so a
#: crafted URL cannot shape local directories or malformed API calls
_OWNER_REPO_RE = re.compile(r"[A-Za-z0-9._-]+")


def parse_repo_url(url: str) -> tuple[str, str]:
    """Parse (owner, repo) from https://github.com/owner/repo (.git or
    /tree/... forms included).
    """
    # urlparse silently strips \n/\t from the URL (bpo-43882), which would
    # rewrite e.g. "abc\n/def" into a different repo than typed — reject
    # control characters up front, before any parsing can hide them
    if any(ord(c) < 0x20 for c in url):
        raise ServiceError(
            "sources",
            ErrorSuffix.INVALID_INPUT,
            f"Invalid GitHub owner/repo in URL: {url}",
            hint="owner and repo may contain letters, digits, '.', '_' and '-' only",
        )
    parsed = urlparse(url.strip())
    if parsed.scheme not in ("http", "https") or parsed.hostname != "github.com":
        raise ServiceError(
            "sources",
            ErrorSuffix.INVALID_INPUT,
            f"Only GitHub repo URLs are supported: {url}",
            hint="e.g. https://github.com/owner/repo",
        )
    parts = [p for p in parsed.path.split("/") if p]
    if len(parts) < 2 or not all(parts[:2]):
        raise ServiceError("sources", ErrorSuffix.INVALID_INPUT, f"Cannot parse repo URL: {url}")
    owner, repo = parts[0], parts[1].removesuffix(".git")
    if (
        not (_OWNER_REPO_RE.fullmatch(owner) and _OWNER_REPO_RE.fullmatch(repo))
        or "." in (owner, repo)
        or ".." in (owner, repo)
    ):
        raise ServiceError(
            "sources",
            ErrorSuffix.INVALID_INPUT,
            f"Invalid GitHub owner/repo in URL: {url}",
            hint="owner and repo may contain letters, digits, '.', '_' and '-' only",
        )
    return owner, repo


@asynccontextmanager
async def client() -> AsyncIterator[httpx.AsyncClient]:
    """One shared AsyncClient for multi-request flows (repo import does
    metadata + README back to back): connection reuse saves one TLS
    handshake per extra request. Single-request callers keep using
    ``_request`` directly; the constructor arguments match ``_request`` so
    tests mocking ``httpx.AsyncClient`` keep working."""
    async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as c:
        yield c


async def _request(
    path: str,
    token: str | None = None,
    params: dict[str, Any] | None = None,
    *,
    client: httpx.AsyncClient | None = None,
) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": _API_VERSION,
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if client is not None:
        resp = await client.get(f"{_API}{path}", headers=headers, params=params)
    else:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as c:
            resp = await c.get(f"{_API}{path}", headers=headers, params=params)
    if resp.status_code == 404:
        raise ServiceError("sources", ErrorSuffix.NOT_FOUND, f"GitHub resource not found: {path}")
    if resp.status_code == 403:
        raise ServiceError(
            "sources",
            ErrorSuffix.RATE_LIMITED,
            "GitHub API rate limited or unauthorized",
            hint="Configure a GitHub token in the settings page to raise the limit",
        )
    resp.raise_for_status()
    return resp.json()


async def fetch_repo_info(
    owner: str, repo: str, token: str | None = None, *, client: httpx.AsyncClient | None = None
) -> dict[str, Any]:
    data = await _request(f"/repos/{owner}/{repo}", token, client=client)
    return {
        "owner": owner,
        "name": data.get("name", repo),
        "url": data.get("html_url", f"https://github.com/{owner}/{repo}"),
        "description": data.get("description") or "",
        "stars": int(data.get("stargazers_count") or 0),
        "language": data.get("language") or "",
    }


async def fetch_readme(
    owner: str, repo: str, token: str | None = None, *, client: httpx.AsyncClient | None = None
) -> str:
    try:
        data = await _request(f"/repos/{owner}/{repo}/readme", token, client=client)
    except ServiceError as exc:
        if exc.body.code.endswith("NOT_FOUND"):
            return ""
        raise
    content = data.get("content") or ""
    if data.get("encoding") == "base64":
        return base64.b64decode(content).decode("utf-8", errors="replace")
    return content


async def search_repos(
    query: str, token: str | None = None, limit: int = 10
) -> list[dict[str, Any]]:
    data = await _request(
        "/search/repositories", token, params={"q": query, "per_page": min(limit, 30)}
    )
    return [
        {
            "owner": (r.get("owner") or {}).get("login", ""),
            "name": r.get("name", ""),
            "url": r.get("html_url", ""),
            "description": r.get("description") or "",
            "stars": int(r.get("stargazers_count") or 0),
            "language": r.get("language") or "",
        }
        for r in data.get("items", [])
    ]


async def list_starred(
    username: str, token: str | None = None, limit: int = 100
) -> list[dict[str, Any]]:
    data = await _request(f"/users/{username}/starred", token, params={"per_page": min(limit, 100)})
    return [
        {
            "owner": (r.get("owner") or {}).get("login", ""),
            "name": r.get("name", ""),
            "url": r.get("html_url", ""),
            "description": r.get("description") or "",
            "stars": int(r.get("stargazers_count") or 0),
            "language": r.get("language") or "",
        }
        for r in data
    ]
