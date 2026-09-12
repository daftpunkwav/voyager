"""Optional HTTP sidecar: python -m graph.engines.python.server.

Hosts the engine in a standalone process (e.g. for large-scale indexing).

Security boundaries (mirroring the C engine's http_server.c HTTP gate):
- Binds to 127.0.0.1 only; rejects non-local Host headers (DNS rebinding);
- POST requires Content-Type: application/json (blocks form-CSRF without preflight);
- index_repository enforces repo_path under ENGINE_ALLOWED_ROOT (rejects escapes).
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .engine import GraphEngine

_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}
_MAX_BODY = 10_000_000  # Request body cap (10MB): prevents oversized bodies from exhausting memory


class Handler(BaseHTTPRequestHandler):
    eng = None
    allowed_root: str | None = None

    def log_message(self, fmt: str, *args) -> None:
        return

    def _reject(self, code: int, message: str) -> None:
        self._json(code, {"error": message})

    def _host_allowed(self) -> bool:
        host = (self.headers.get("Host") or "").strip()
        if not host:
            return False
        hostname = host.rsplit(":", 1)[0].strip("[]")
        return hostname in _LOCAL_HOSTS

    def _content_type_ok(self) -> bool:
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        return ctype == "application/json"

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if not self._host_allowed():
            self._reject(403, "forbidden")
            return
        eng = Handler.eng
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._json(200, {"status": "ok", "engine": "graph-engine"})
            return
        if parsed.path == "/api/layout":
            qs = parse_qs(parsed.query)
            project = (qs.get("project") or [""])[0]
            max_nodes = int((qs.get("max_nodes") or ["5000"])[0])
            self._json(200, eng.fetch_layout(project, max_nodes=max_nodes))
            return
        if parsed.path == "/api/cross-edges":
            self._json(200, {"edges": eng.list_cross_edges()})
            return
        self._json(404, {"error": "not_found"})

    def do_POST(self) -> None:
        if not self._host_allowed():
            self._reject(403, "forbidden")
            return
        if not self._content_type_ok():
            self._reject(415, "unsupported_media_type")
            return
        eng = Handler.eng
        length = int(self.headers.get("Content-Length") or 0)
        if length > _MAX_BODY:
            self._json(413, {"error": "payload_too_large"})
            return
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            self._json(400, {"error": "invalid_json"})
            return
        if urlparse(self.path).path != "/rpc":
            self._json(404, {"error": "not_found"})
            return
        params = data.get("params") or {}
        name = params.get("name")
        args = params.get("arguments") or {}
        try:
            result = _dispatch(eng, name, args)
            self._json(200, {"jsonrpc": "2.0", "id": data.get("id"), "result": result})
        except Exception as exc:
            self._json(
                200,
                {
                    "jsonrpc": "2.0",
                    "id": data.get("id"),
                    "error": {"message": str(exc)},
                },
            )


def _dispatch(eng, name: str, args: dict):
    if name == "index_repository":
        repo_path = args.get("repo_path") or "."
        _assert_within_allowed_root(repo_path)
    # Dispatch uniformly via GraphEngine.call (same mapping as client._sync_call)
    return eng.call(name, args)


def _assert_within_allowed_root(repo_path: str) -> None:
    """Enforce the indexing boundary: repo_path must lie under ENGINE_ALLOWED_ROOT; reject otherwise."""
    root = Handler.allowed_root
    if not root:
        return  # No boundary when allowed_root is unset (matches the C engine's behavior)
    root_resolved = Path(root).resolve()
    target = Path(repo_path).resolve()
    if target != root_resolved and root_resolved not in target.parents:
        raise ValueError(f"repo_path outside the allowed root: {repo_path} is not under {root}")


def main() -> None:
    # The engine layer reads ENGINE_* uniformly (single authoritative names, same
    # as the C engine's getenv); the application layer addresses the sidecar
    # through the graph.engine.c_url setting, not through these variables.
    root = os.environ.get("ENGINE_ALLOWED_ROOT")
    port = int(os.environ.get("ENGINE_PORT") or "9750")
    Handler.eng = GraphEngine(data_root=root)
    Handler.allowed_root = root
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"graph-engine listening on 127.0.0.1:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
