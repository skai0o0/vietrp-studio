from __future__ import annotations

from pathlib import Path

import httpx

from app import __version__
from app.main import create_app
from tests.conftest import make_settings


async def test_health(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


async def test_unknown_api_path_uses_error_body(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/nope")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_cors_enabled_in_dev_only() -> None:
    origin = "http://localhost:5173"
    for env, expected in (("dev", origin), ("prod", None)):
        app = create_app(make_settings(env=env))
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as http_client:
            response = await http_client.get("/api/health", headers={"Origin": origin})
        assert response.headers.get("access-control-allow-origin") == expected


async def test_spa_fallback_serves_built_frontend(tmp_path: Path) -> None:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>spa</html>")
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    app = create_app(make_settings(frontend_dist_dir=tmp_path))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as http_client:
        assert (await http_client.get("/library/characters")).text == "<html>spa</html>"
        assert (await http_client.get("/assets/app.js")).text == "console.log(1)"
        assert (await http_client.get("/api/health")).json()["status"] == "ok"
        missing_api = await http_client.get("/api/missing")
        assert missing_api.status_code == 404
        assert missing_api.json()["error"]["code"] == "not_found"
        traversal = await http_client.get("/..%2f..%2fpyproject.toml")
        assert "vietrp-studio-backend" not in traversal.text


async def test_no_static_mount_without_dist(client: httpx.AsyncClient) -> None:
    response = await client.get("/")
    assert response.status_code == 404
