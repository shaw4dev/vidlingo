import os

# Before any app module reads it: tests must never reach a real database file.
# A test that forgets the session fixtures would otherwise use whatever
# DATABASE_URL points at — a populated dev.db on a developer's machine, an
# empty file on a clean checkout — and pass locally while failing in CI.
# Pointing it at a throwaway in-memory URL turns that into an immediate,
# obvious "no such table" instead of a difference between two machines.
os.environ["DATABASE_URL"] = "sqlite://"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app.db import models  # noqa: F401, E402  (register tables)
from app.db.base import Base  # noqa: E402
from app.db.session import get_session  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture
def engine():
    """A shared in-memory SQLite DB (StaticPool keeps one connection, so the
    schema persists across the multiple sessions a request flow opens)."""
    eng = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        future=True,
    )
    Base.metadata.create_all(eng)
    try:
        yield eng
    finally:
        eng.dispose()


@pytest.fixture
def session_factory(engine):
    return sessionmaker(bind=engine, expire_on_commit=False, class_=Session)


@pytest.fixture
def db(session_factory) -> Session:
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(session_factory) -> TestClient:
    """TestClient with get_session overridden to use the in-memory DB."""

    def _override():
        s = session_factory()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_session] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()
