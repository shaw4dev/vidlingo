"""VidLingo API entrypoint.

A modular monolith (see architecture.md §5.1): feature modules register their
routers here.

In the deployed image this process also serves the built web client, so the
whole app is one container (STATIC_DIR). In development it doesn't: Vite serves
the client and proxies /api here, which is what keeps hot reload working.
"""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.config import settings
from app.routers import auth, content, health, vocab


def _mount_client(app: FastAPI, static_dir: Path) -> None:
    """Serve the built SPA alongside the API.

    Two wrinkles a plain static mount doesn't handle:

    Deep links. `/reader/<id>` is a client route with no file behind it, so
    StaticFiles 404s and a refresh breaks the app. The SPA has to answer every
    unmatched path with index.html — but only for a browser. Keying that on
    `Accept: text/html` keeps real API 404s as JSON: fetch() sends `*/*`, which
    doesn't match, so `GET /lessons/nope` still says "Lesson not found".

    Mount order. This runs after the routers are registered, so an API path is
    always matched by its route first and never shadowed by the catch-all.
    """
    index = static_dir / "index.html"

    app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

    @app.exception_handler(StarletteHTTPException)
    async def spa_fallback(request: Request, exc: StarletteHTTPException):
        wants_html = "text/html" in request.headers.get("accept", "")
        if exc.status_code == 404 and request.method == "GET" and wants_html:
            return FileResponse(index)
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)

    @app.get("/", include_in_schema=False)
    async def spa_root() -> FileResponse:
        return FileResponse(index)


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

    # Only in the deployed image; absent in dev, where Vite serves the client.
    static_dir = Path(settings.static_dir) if settings.static_dir else None
    if static_dir and (static_dir / "index.html").is_file():
        _mount_client(app, static_dir)

    return app


app = create_app()
