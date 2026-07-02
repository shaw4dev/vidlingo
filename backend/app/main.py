"""VidLingo API entrypoint.

A modular monolith (see architecture.md §5.1): feature modules register their
routers here.
"""

from fastapi import FastAPI

from app import __version__
from app.routers import auth, content, health


def create_app() -> FastAPI:
    app = FastAPI(
        title="VidLingo API",
        version=__version__,
        summary="Backend for the VidLingo video English-learning app.",
    )
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(content.router)
    return app


app = create_app()
