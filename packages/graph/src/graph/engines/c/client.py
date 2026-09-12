"""HTTP + JSON-RPC client for the C engine sidecar.

Two flavors: sidecar RPC (synchronous index) and native engine
(POST /api/index + /api/index-status polling). The in-process engine does
not go through this module (fallback logic lives in engines/adapter.py);
errors are raised uniformly as contracts.ServiceError.
"""

from __future__ import annotations

import asyncio
from typing import Any, Literal

import httpx
from platform_contracts import ErrorSuffix, ServiceError

_DOMAIN = "graph"
EngineFlavor = Literal["sidecar_rpc", "native", "unknown"]


class CEngineClient:
    """HTTP + JSON-RPC client for the C engine sidecar. Empty base_url = not configured."""

    def __init__(
        self, base_url: str, *, timeout: float = 300.0, poll_interval: float = 2.0
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.poll_interval = poll_interval
        self._rpc_id = 0

    async def health(self) -> bool:
        if not self.base_url:
            return False
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{self.base_url}/api/project-health")
                return resp.status_code == 200
        except Exception:  # noqa: BLE001  # a failed probe means unavailable; the adapter falls back
            return False

    async def call(self, name: str, args: dict[str, Any] | None = None) -> Any:
        """JSON-RPC tools/call:search_graph / trace_path / get_graph_schema …"""
        self._rpc_id += 1
        payload = {
            "jsonrpc": "2.0",
            "id": self._rpc_id,
            "method": "tools/call",
            "params": {"name": name, "arguments": args or {}},
        }
        data = await self._post("/rpc", payload)
        if "error" in data:
            raise ServiceError(
                _DOMAIN, ErrorSuffix.INTERNAL, f"C engine RPC error: {data['error']}"
            )
        return data.get("result")

    async def index_repository(
        self, repo_path: str, *, name: str | None = None, mode: str = "moderate"
    ) -> dict[str, Any]:
        """Native indexing: POST /api/index, then poll /api/index-status until idle."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                f"{self.base_url}/api/index",
                json={"repo_path": repo_path, "name": name or "", "mode": mode},
            )
            if resp.status_code >= 400:
                raise ServiceError(
                    _DOMAIN,
                    ErrorSuffix.INTERNAL,
                    f"C engine index start failed: HTTP {resp.status_code}",
                )
            while True:
                await asyncio.sleep(self.poll_interval)
                st = await client.get(f"{self.base_url}/api/index-status")
                status = st.json()
                if not status.get("indexing", False):
                    if status.get("error"):
                        raise ServiceError(
                            _DOMAIN,
                            ErrorSuffix.INTERNAL,
                            f"C engine indexing failed: {status['error']}",
                        )
                    return {"project": name or repo_path, "status": "indexed", "detail": status}

    async def _post(self, path: str, payload: dict[str, Any]) -> Any:
        if not self.base_url:
            raise ServiceError(_DOMAIN, ErrorSuffix.UNAVAILABLE, "C engine base_url not configured")
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(f"{self.base_url}{path}", json=payload)
        except httpx.HTTPError as exc:
            raise ServiceError(
                _DOMAIN, ErrorSuffix.UNAVAILABLE, f"C engine unreachable: {exc}"
            ) from exc
        if resp.status_code >= 400:
            raise ServiceError(
                _DOMAIN,
                ErrorSuffix.INTERNAL,
                f"C engine HTTP {resp.status_code}: {resp.text[:200]}",
            )
        return resp.json()
