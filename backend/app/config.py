"""Runtime configuration.

DATABASE_URL drives everything DB-related. Defaults to a local SQLite file so the
app and tests run with zero setup; in Docker/AWS (T09/T10) it points at Postgres,
e.g. postgresql+psycopg://user:pass@host:5432/vidlingo
"""

from __future__ import annotations

import os


class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./dev.db")


settings = Settings()
