"""Router registry. Each work package adds its routers inside `include_routers`."""

from fastapi import FastAPI

from app.api import assets, chats, creator, gallery, library, presets, secrets, turns, utility, vault
from app.api import io as io_api


def include_routers(app: FastAPI) -> None:
    """Mount every API router on the app."""
    app.include_router(vault.router)
    app.include_router(secrets.router)
    for router in library.ROUTERS:
        app.include_router(router)
    app.include_router(gallery.router)
    app.include_router(assets.router)
    app.include_router(io_api.router)
    app.include_router(creator.router)
    app.include_router(chats.router)
    app.include_router(chats.messages_router)
    app.include_router(turns.router)
    app.include_router(presets.router)
    app.include_router(utility.router)
