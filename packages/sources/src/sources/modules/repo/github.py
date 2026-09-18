"""GitHub API client: metadata / README / search / starred.

All requests go through the single `_request` outlet (easy to mock in
tests and to handle rate limits). Tokens are passed in by callers via
secrets; the client never touches secret storage. Cloning lives in the
worker, not here.
"""

from __future__ import annotations

import base64
import re
from typing import Any

import httpx
from platform_contracts import ErrorSuffix, ServiceError

_API = "https://api.github.com"
_TIMEOUT = httpx.Timeout(connect=10.0, read=30.0, write=10.0, pool=10.0)

#: Owner/repo names feed the clone destination (workspace/repo/{owner}__{repo})
#: and API paths; anything outside GitHub's charset is rejected up front so a
#: crafted URL cannot shape local directories or malformed API calls
_OWNER_REPO_RE = re.compile(r"^[A-Za-z0-9._-]+$")


def parse_repo_url(url: str) -> tuple[str, str]:
    """Parse (owner, repo) from https://github.com/owner/repo (.git or
    /tree/... forms included).
    """
    text = url.strip().removesuffix(".git").rstrip("/")
    if "github.com" not in text:
        raise ServiceError(
            "sources",
            ErrorSuffix.INVALID_INPUT,
            f"Only GitHub repo URLs are supported: {url}",
            hint="e.g. https://github.com/owner/repo",
        )
    parts = text.split("github.com/", 1)[1].split("/")
    if len(parts) < 2 or not all(parts[:2]):
        raise ServiceError("sources", ErrorSuffix.INVALID_INPUT, f"Cannot parse repo URL: {url}")
    owner, repo = parts[0], parts[1]
    if (
        not (_OWNER_REPO_RE.match(owner) and _OWNER_REPO_RE.match(repo))
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


async def _request(
    path: str, token: str | None = None, params: dict[str, Any] | None = None
) -> Any:
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
        resp = await client.get(f"{_API}{path}", headers=headers, params=params)
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


async def fetch_repo_info(owner: str, repo: str, token: str | None = None) -> dict[str, Any]:
    data = await _request(f"/repos/{owner}/{repo}", token)
    return {
        "owner": owner,
        "name": data.get("name", repo),
        "url": data.get("html_url", f"https://github.com/{owner}/{repo}"),
        "description": data.get("description") or "",
        "stars": int(data.get("stargazers_count") or 0),
        "language": data.get("language") or "",
    }


async def fetch_readme(owner: str, repo: str, token: str | None = None) -> str:
    try:
        data = await _request(f"/repos/{owner}/{repo}/readme", token)
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
