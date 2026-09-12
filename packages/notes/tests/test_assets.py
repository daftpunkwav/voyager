"""Asset capability tests: add_asset whitelist/size/workspace boundaries,
read-only routes, purge cleanup.
"""

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from notes.capabilities import registry
from notes.wiring import wire
from platform_actor import ActorContext
from platform_capability import execute
from platform_contracts import LOCAL_USER, ServiceError

USER_CTX = ActorContext(actor=LOCAL_USER)

_PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 64


@pytest.fixture()
def env(tmp_path):
    """Full wire() assembly (workspace pointed at tmp) plus a standalone FastAPI
    app mounting the asset routes.
    """
    from platform_eventbus import EventBus, EventLog

    bus = EventBus(EventLog(tmp_path / "events.db"))
    w = wire(tmp_path / "data", bus=bus, workspace=tmp_path / "ws")
    (tmp_path / "ws").mkdir(exist_ok=True)
    app = FastAPI()
    from fastapi.responses import JSONResponse
    from notes.assets import build_assets_router
    from platform_contracts import ServiceError as SE

    app.include_router(build_assets_router(), prefix="/api/notes")

    @app.exception_handler(SE)
    async def _se(_req, exc: SE) -> JSONResponse:
        return JSONResponse(status_code=exc.http_status, content=exc.to_envelope())

    yield w, tmp_path / "ws", TestClient(app)
    if w.close:
        w.close()
    bus.log.close() if hasattr(bus, "log") else None


class TestAddAsset:
    async def test_add_returns_markdown_reference(self, env) -> None:
        _, ws, _ = env
        src = ws / "pic.png"
        src.write_bytes(_PNG)
        out = await execute(
            registry, "add_asset", USER_CTX, {"file_path": str(src), "filename": "screenshot.png"}
        )
        assert out["asset_id"]
        assert out["url"] == f"/api/notes/assets/{out['asset_id']}"
        assert out["markdown"] == f"![screenshot.png](attachment://{out['asset_id']})"
        # The copy lands in notes-assets, named by id (content-addressed, never overwritten).
        assert (
            Path(out["url"].rsplit("/", 1)[-1]).suffix == ".png"
            or (ws / "notes-assets" / f"{out['asset_id']}.png").is_file()
        )

    async def test_rejects_non_image_and_missing(self, env, tmp_path) -> None:
        _, ws, _ = env
        bad = ws / "evil.exe"
        bad.write_bytes(b"MZ")
        with pytest.raises(ServiceError, match="Unsupported image format"):
            await execute(registry, "add_asset", USER_CTX, {"file_path": str(bad)})
        with pytest.raises(ServiceError, match="File not found"):
            await execute(registry, "add_asset", USER_CTX, {"file_path": str(ws / "nope.png")})

    async def test_rejects_outside_workspace(self, env, tmp_path) -> None:
        _, _ws, _ = env
        outside = tmp_path / "outside.png"
        outside.write_bytes(_PNG)
        with pytest.raises(ServiceError, match="workspace"):
            await execute(registry, "add_asset", USER_CTX, {"file_path": str(outside)})

    async def test_rejects_symlink_outside_workspace(self, env, tmp_path) -> None:
        """A symlink pointing outside the workspace must still be rejected."""
        _, ws, _ = env
        real = tmp_path / "secret.png"
        real.write_bytes(_PNG)
        link = ws / "link.png"
        try:
            link.symlink_to(real)
        except OSError:
            pytest.skip("symlink not supported in this environment")
        with pytest.raises(ServiceError, match="workspace"):
            await execute(registry, "add_asset", USER_CTX, {"file_path": str(link)})


class TestAssetRoute:
    async def test_get_asset_file(self, env) -> None:
        _, ws, client = env
        src = ws / "p.png"
        src.write_bytes(_PNG)
        out = await execute(registry, "add_asset", USER_CTX, {"file_path": str(src)})
        resp = client.get(f"/api/notes/assets/{out['asset_id']}")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("image/png")
        assert resp.headers.get("cache-control") == "public, max-age=31536000, immutable"
        missing = client.get("/api/notes/assets/ghost")
        assert missing.status_code == 404


class TestPurgeCleansAssets:
    async def test_purge_note_removes_asset_files(self, env) -> None:
        _, ws, _ = env
        note = await execute(
            registry, "create_note", USER_CTX, {"title": "note with image", "content": "has image"}
        )
        nid = note["id"]
        src = ws / "p2.png"
        src.write_bytes(_PNG)
        asset = await execute(
            registry, "add_asset", USER_CTX, {"file_path": str(src), "note_id": nid}
        )
        asset_file = ws / "notes-assets" / f"{asset['asset_id']}.png"
        assert asset_file.is_file()
        await execute(registry, "purge_note", USER_CTX, {"note_id": nid})
        assert not asset_file.exists()  # purge also removes attachment files


class TestRegistryCard:
    def test_service_json_includes_add_asset(self) -> None:
        import json

        card = json.loads((Path(__file__).resolve().parents[1] / "service.json").read_text("utf-8"))
        assert "add_asset" in card["capabilities"]
        assert set(card["capabilities"]) == set(registry.names())
