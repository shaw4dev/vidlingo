"""Runtime configuration.

DATABASE_URL drives everything DB-related. Defaults to a local SQLite file so the
app and tests run with zero setup; in Docker/AWS (T09/T10) it points at Postgres,
e.g. postgresql+psycopg://user:pass@host:5432/vidlingo
"""

from __future__ import annotations

import os


class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./dev.db")

    # Auth. SECRET_KEY MUST be set to a strong random value in prod (T10).
    secret_key: str = os.getenv("SECRET_KEY", "dev-insecure-change-me")
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "10080"))

    # Content discovery (YouTube Data API v3). Optional: only the sourcing jobs
    # need it; the app and the rest of the pipeline run without it.
    youtube_api_key: str | None = os.getenv("YOUTUBE_API_KEY")

    # Browser origins allowed to call the API, comma-separated. Empty in dev:
    # Vite proxies /api to :8000, so the browser stays same-origin and CORS
    # never enters the picture (ADR-002). It only becomes real once the built
    # client is served from its own host, which is what deployment does.
    cors_origins: list[str] = [
        o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()
    ]


settings = Settings()
