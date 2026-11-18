"""The end-to-end vault flow, shared by the fake-repository and real-Postgres tests."""

from __future__ import annotations

import httpx

# Dummy value, not a real key.
SECRET_VALUE = "sk-or-v1-DUMMYVALUE-0123456789abcd"
SECRET_NAME = "OPENROUTER_API_KEY"


async def run_vault_flow(client: httpx.AsyncClient, passphrase: str, caplog_text: object | None = None) -> None:
    bodies: list[str] = []

    def keep(response: httpx.Response) -> httpx.Response:
        bodies.append(response.text + str(response.headers))
        return response

    # Unknown passphrase: exists false, no cookie.
    r = keep(await client.post("/api/vault/unlock", json={"passphrase": passphrase}))
    assert r.status_code == 200
    assert r.json() == {"exists": False, "vault": None}
    assert "vietrp_session" not in r.headers.get("set-cookie", "")

    # Create.
    r = keep(await client.post("/api/vault/create", json={"passphrase": passphrase, "display_name": "Nem"}))
    assert r.status_code == 201
    cookie = r.headers["set-cookie"].lower()
    assert "vietrp_session=" in cookie and "httponly" in cookie and "samesite=strict" in cookie and "path=/" in cookie
    vault = r.json()["vault"]
    assert vault["display_name"] == "Nem" and set(vault) == {"id", "display_name", "created_at"}

    # Duplicate create.
    r = keep(await client.post("/api/vault/create", json={"passphrase": passphrase, "display_name": "Other"}))
    assert r.status_code == 409 and r.json()["error"]["code"] == "vault_exists"

    # me, rename.
    r = keep(await client.get("/api/vault/me"))
    assert r.status_code == 200 and r.json()["vault"]["id"] == vault["id"]
    r = keep(await client.patch("/api/vault/me", json={"display_name": "  Nem 2 "}))
    assert r.status_code == 200 and r.json()["vault"]["display_name"] == "Nem 2"
    r = keep(await client.patch("/api/vault/me", json={"display_name": ""}))
    assert r.status_code == 422 and r.json()["error"]["code"] == "validation_error"

    # Secrets: nothing set yet.
    r = keep(await client.get("/api/secrets"))
    assert r.status_code == 200
    assert r.json() == {"secrets": [{"name": SECRET_NAME, "is_set": False, "hint": None, "updated_at": None}]}

    r = keep(await client.put("/api/secrets/NOT_ALLOWED", json={"value": SECRET_VALUE}))
    assert r.status_code == 400 and r.json()["error"]["code"] == "secret_name_invalid"
    r = keep(await client.put(f"/api/secrets/{SECRET_NAME}", json={"value": "   "}))
    assert r.status_code == 422
    r = keep(await client.put(f"/api/secrets/{SECRET_NAME}", json={"value": f"  {SECRET_VALUE} "}))
    assert r.status_code == 200
    secret = r.json()["secret"]
    assert secret["is_set"] is True and secret["hint"] == SECRET_VALUE[-4:] and secret["updated_at"]

    r = keep(await client.get("/api/secrets"))
    entry = r.json()["secrets"][0]
    assert entry["is_set"] is True and entry["hint"] == SECRET_VALUE[-4:]

    # Lock clears the session.
    r = keep(await client.post("/api/vault/lock"))
    assert r.status_code == 204
    client.cookies.clear()
    r = keep(await client.get("/api/vault/me"))
    assert r.status_code == 401 and r.json()["error"]["code"] == "vault_locked"
    r = keep(await client.get("/api/secrets"))
    assert r.status_code == 401

    # Unlock again with the right passphrase: the stored secret survives, a wrong one finds nothing.
    r = keep(await client.post("/api/vault/unlock", json={"passphrase": passphrase + "x"}))
    assert r.json() == {"exists": False, "vault": None}
    r = keep(await client.post("/api/vault/unlock", json={"passphrase": passphrase}))
    assert r.status_code == 200 and r.json()["exists"] is True and r.json()["vault"]["id"] == vault["id"]
    r = keep(await client.get("/api/secrets"))
    assert r.json()["secrets"][0]["is_set"] is True

    r = keep(await client.delete(f"/api/secrets/{SECRET_NAME}"))
    assert r.status_code == 204
    r = keep(await client.delete("/api/secrets/NOT_ALLOWED"))
    assert r.status_code == 400
    r = keep(await client.get("/api/secrets"))
    assert r.json()["secrets"][0]["is_set"] is False

    for body in bodies:
        assert SECRET_VALUE not in body
        assert passphrase not in body
    if isinstance(caplog_text, str):
        assert SECRET_VALUE not in caplog_text
        assert passphrase not in caplog_text
