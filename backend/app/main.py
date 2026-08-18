"""VidLingo API entrypoint.

A modular monolith (see architecture.md §5.1): feature modules register their
routers here.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.config import settings
from app.routers import auth, content, health, vocab


def create_app() -> FastAPI:
    app = FastAPI(
        title="VidLingo API",
        version=__version__,
        summary="Backend for the VidLingo video English-learning app.",
    )
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_methods=["*"],
            allow_headers=["*"],
            # Auth is a Bearer header, not a cookie, so credentialed requests
            # aren't needed — and not allowing them keeps the origin list strict.
            allow_credentials=False,
        )

    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(content.router)
    app.include_router(vocab.router)
    return app


app = create_app()
