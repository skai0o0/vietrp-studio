from __future__ import annotations

import httpx
from fastapi import FastAPI
from pydantic import BaseModel

from app.core.errors import AppError


class Payload(BaseModel):
    passphrase: str


def _add_routes(app: FastAPI) -> None:
    @app.get("/api/_test/app-error")
    async def app_error() -> None:
        raise AppError("vault_not_found", "No such vault", 404, headers={"Retry-After": "7"})

    @app.post("/api/_test/validate")
    async def validate(payload: Payload) -> None:
        _ = payload

    @app.get("/api/_test/boom")
    async def boom() -> None:
        raise RuntimeError("secret internal detail")


async def test_app_error_body(app: FastAPI, client: httpx.AsyncClient) -> None:
    _add_routes(app)
    response = await client.get("/api/_test/app-error")
    assert response.status_code == 404
    assert response.json() == {"error": {"code": "vault_not_found", "message": "No such vault"}}
    assert response.headers["retry-after"] == "7"


async def test_validation_error_body_does_not_echo_input(app: FastAPI, client: httpx.AsyncClient) -> None:
    _add_routes(app)
    response = await client.post("/api/_test/validate", json={"passphrase": 123, "extra": "hunter2-secret"})
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "validation_error"
    assert "passphrase" in body["error"]["message"]
    assert "hunter2-secret" not in response.text
    assert "123" not in body["error"]["message"]


async def test_unhandled_error_hides_details(app: FastAPI, client: httpx.AsyncClient) -> None:
    _add_routes(app)
    response = await client.get("/api/_test/boom")
    assert response.status_code == 500
    assert response.json() == {"error": {"code": "internal_error", "message": "Internal server error"}}
    assert "secret internal detail" not in response.text
    assert "Traceback" not in response.text
