"""Repo submodule capabilities: import / list / sort / README / metadata /
remote search.

Import is a long-running task: register -> enqueue clone -> emit
source.ready on completion. The GitHub token lives in platform/secrets
and only the user may write it (same boundary as the LLM key).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from platform_capability import Registry, capability
from platform_contracts import (
    ActorKind,
    ActorRef,
    DomainEvent,
    ErrorSuffix,
    Event,
    JobRef,
    ServiceError,
)
from platform_eventbus import EventBus
from platform_secrets import SecretStore

from .._shared.events import with_session
from . import github
from .store import RepoStore

_DOMAIN = "sources"
registry = Registry(_DOMAIN)

_TOKEN_KEY = "sources.github.token"
_REPO_ACTOR = ActorRef(kind=ActorKind.SYSTEM, id="sources.repo")


@dataclass
class RepoDeps:
    store: RepoStore
    secrets: SecretStore
    bus: EventBus | None
    queue: asyncio.Queue  # clone jobs: repo_id
    workspace: Path  # clone destination root (workspace/repo/)


_deps: RepoDeps | None = None


def init_deps(deps: RepoDeps) -> None:
    global _deps
    _deps = deps


def require_deps() -> RepoDeps:
    if _deps is None:
        raise RuntimeError("deps not injected: call init_deps() at the service entry point first")
    return _deps


def _token() -> str | None:
    return _deps.secrets.get(_TOKEN_KEY) if _deps else None


def _require_repo(rid: str) -> dict[str, Any]:
    repo = require_deps().store.get(rid)
    if repo is None:
        raise ServiceError(_DOMAIN, ErrorSuffix.NOT_FOUND, f"Repo not found: {rid}")
    return repo


@capability(
    registry,
    name="import_repo",
    description="Import a GitHub repo: register metadata + README, clone in background",
    long_running=True,
    cost=5,
)
async def import_repo(url: str, category: str = "", clone: bool = True) -> JobRef:
    deps = require_deps()
    owner, name = github.parse_repo_url(url)
    existing = deps.store.get_by_url(f"https://github.com/{owner}/{name}")
    if existing and existing["status"] == "ready":
        raise ServiceError(
            _DOMAIN,
            ErrorSuffix.CONFLICT,
            f"Repo already imported: {owner}/{name}",
            hint="See list_repos; remove_repo first before re-importing",
        )
    info = await github.fetch_repo_info(owner, name, _token())
    readme = await github.fetch_readme(owner, name, _token())
    rid = deps.store.add(
        {**info, "category": category, "readme": readme, "status": "importing", "source": "github"}
    )
    if deps.bus is not None:
        await deps.bus.publish(
            Event(
                type=DomainEvent.SOURCE_ADDED,
                actor=_REPO_ACTOR,
                payload=with_session({"source_id": rid, "kind": "repo", "name": f"{owner}/{name}"}),
            )
        )
    if clone:
        deps.queue.put_nowait(rid)
    else:
        deps.store.set_status(rid, "ready")
    return JobRef(job_id=rid)


@capability(registry, name="list_repos", description="Repo list (summaries, no README)")
def list_repos(sort: str = "added", desc: bool = True, category: str = "") -> list[dict]:
    return require_deps().store.list(sort=sort, desc=desc, category=category)


@capability(registry, name="sort_repos", description="Sort by field: name/stars/added/updated")
def sort_repos(by: str = "name", desc: bool = False) -> list[dict]:
    """Sort projects by name -- a capability for users and agents alike."""
    return require_deps().store.list(sort=by, desc=desc)


@capability(registry, name="get_readme", description="Fetch a repo's full README on demand")
def get_readme(repo_id: str) -> dict:
    repo = _require_repo(repo_id)
    return {"repo_id": repo_id, "name": repo["name"], "readme": repo["readme"]}


@capability(registry, name="get_repo", description="Single repo detail (README included)")
def get_repo(repo_id: str) -> dict:
    return _require_repo(repo_id)


@capability(
    registry,
    name="set_repo_meta",
    description="Set category/tags/progress/note (supersedes the legacy categories+tags+progress)",
)
def set_repo_meta(
    repo_id: str,
    category: str | None = None,
    tags: list[str] | None = None,
    progress: str | None = None,
    note: str | None = None,
) -> dict:
    deps = require_deps()
    _require_repo(repo_id)
    deps.store.set_meta(repo_id, category=category, tags=tags, progress=progress, note=note)
    updated = deps.store.get(repo_id, with_readme=False)
    if updated is None:  # unreachable: _require_repo above verified the row
        raise ServiceError(_DOMAIN, ErrorSuffix.NOT_FOUND, f"Repo not found: {repo_id}")
    return updated


@capability(registry, name="list_categories", description="Existing categories (distinct)")
def list_categories() -> list[str]:
    return require_deps().store.categories()


def _within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(Path(root).resolve())
        return True
    except ValueError:
        return False


@capability(
    registry,
    name="remove_repo",
    description="Delete a repo's record and local clone",
    reversible=False,
    cost=2,
)
async def remove_repo(repo_id: str) -> dict:
    deps = require_deps()
    repo = _require_repo(repo_id)
    deps.store.remove(repo_id)
    if repo["local_path"] and _within(Path(repo["local_path"]), deps.workspace):
        # Local directory cleanup is done asynchronously by the worker
        # (same queue as cloning, order preserved). Jail check before
        # queueing: the worker rmtrees the stored path without further
        # validation, so a tampered/stale row must never escape workspace/.
        deps.queue.put_nowait(("remove", repo_id, repo["local_path"]))
    if deps.bus is not None:
        # Same removal receipt as the doc/web submodules: sources-page query
        # invalidation and the activity feed both key on source.removed
        display = f"{repo['owner']}/{repo['name']}" if repo.get("owner") else str(repo["name"])
        await deps.bus.publish(
            Event(
                type=DomainEvent.SOURCE_REMOVED,
                actor=_REPO_ACTOR,
                payload=with_session({"source_id": repo_id, "kind": "repo", "name": display}),
            )
        )
    return {"removed": repo_id, "name": repo["name"], "local_path": repo["local_path"]}


@capability(
    registry,
    name="search_remote_repos",
    description="Search GitHub repos (candidates not yet imported)",
    cost=3,
)
async def search_remote_repos(query: str, limit: int = 10) -> list[dict]:
    return await github.search_repos(query, _token(), limit)


@capability(
    registry, name="list_starred_repos", description="List a GitHub account's starred repos", cost=3
)
async def list_starred_repos(username: str, limit: int = 100) -> list[dict]:
    return await github.list_starred(username, _token(), limit)


@capability(
    registry, name="set_github_token", description="Set the GitHub token (secret: user only)"
)
def set_github_token(token: str, _actor: ActorRef | None = None) -> dict:
    if _actor is None or _actor.kind is not ActorKind.USER:
        raise ServiceError(
            _DOMAIN,
            ErrorSuffix.FORBIDDEN,
            "GitHub tokens are private data; only the user themself may set one",
        )
    require_deps().secrets.set(_TOKEN_KEY, token)
    return {"has_token": True}
