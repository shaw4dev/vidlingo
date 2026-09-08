"""Engine + session factory derived from settings.database_url."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings


def make_engine(url: str | None = None):
    url = url or settings.database_url
    # SQLite needs this when used across FastAPI's threadpool.
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    # Neon suspends its compute after a few minutes idle and drops every
    # connection with it. The pool cannot tell, so it hands out a dead socket
    # and the request 500s -- intermittently, and only after quiet periods,
    # which is the worst shape a bug can have. pre_ping spends one round trip
    # per checkout to find out; recycle retires connections before an idle
    # timeout can. Neither applies to SQLite, which has no server to lose.
    pool_args = {} if url.startswith("sqlite") else {"pool_pre_ping": True, "pool_recycle": 300}
    engine = create_engine(url, future=True, connect_args=connect_args, **pool_args)

    if url.startswith("sqlite"):
        # SQLite ignores foreign keys unless asked, per connection. Without this
        # the dev DB silently accepts what Postgres would reject, so an ondelete
        # rule that works in prod appears broken locally (and vice versa).
        @event.listens_for(engine, "connect")
        def _enable_sqlite_fks(dbapi_conn, _record):  # pragma: no cover - driver hook
            cur = dbapi_conn.cursor()
            cur.execute("PRAGMA foreign_keys=ON")
            cur.close()

    return engine


engine = make_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, class_=Session)


def get_session() -> Iterator[Session]:
    """FastAPI dependency: yields a session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
