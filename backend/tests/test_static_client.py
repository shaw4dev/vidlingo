"""T10: the deployed image serves the SPA and the API from one process."""

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import create_app


@pytest.fixture
def spa(tmp_path, monkeypatch):
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "index.html").write_text("<!doctype html><title>VidLingo</title>", encoding="utf-8")
    monkeypatch.setattr(settings, "static_dir", str(tmp_path))
    with TestClient(create_app()) as c:
        yield c


def test_serves_the_client_at_the_root(spa):
    r = spa.get("/")
    assert r.status_code == 200
    assert "VidLingo" in r.text


def test_deep_link_falls_back_to_index_for_a_browser(spa):
    """A refresh on /reader/<id> must not 404 — there is no such file, the
    route only exists inside the SPA."""
    r = spa.get("/reader/yt_abc", headers={"Accept": "text/html"})
    assert r.status_code == 200
    assert "VidLingo" in r.text


def test_api_404s_stay_json_for_api_clients(spa):
    """fetch() sends Accept: */*, which must not be mistaken for a browser
    navigation — otherwise every API error returns an HTML page."""
    r = spa.get("/api/lessons/does-not-exist", headers={"Accept": "*/*"})
    assert r.status_code == 404
    assert r.json()["detail"] == "Lesson not found"


def test_static_assets_are_served(spa):
    assert spa.get("/assets/app.js").status_code == 200


def test_without_a_static_dir_nothing_is_mounted(monkeypatch):
    """Development: Vite owns the client, so the API must not answer for it."""
    monkeypatch.setattr(settings, "static_dir", None)
    with TestClient(create_app()) as c:
        assert c.get("/", headers={"Accept": "text/html"}).status_code == 404


def test_a_path_that_is_both_a_page_and_an_endpoint_serves_the_page(spa):
    """`/vocab` is a client route AND an API route.

    With the API mounted at the root they collided: the endpoint matched first
    and a browser navigating to /vocab got `401 Not authenticated` — not a 404,
    so the SPA fallback never fired. Mounting the API under /api separates the
    namespaces; this pins that they stay separated.
    """
    page = spa.get("/vocab", headers={"Accept": "text/html"})
    assert page.status_code == 200
    assert "VidLingo" in page.text

    api = spa.get("/api/vocab", headers={"Accept": "*/*"})
    assert api.status_code == 401  # still guarded, still JSON
    assert api.json()["detail"]


def test_every_api_route_lives_under_the_prefix(spa):
    """A route added at the root would be invisible to the client (whose base
    is /api) and would shadow any client page of the same name."""
    from app.main import API_PREFIX

    paths = {r.path for r in spa.app.routes if getattr(r, "path", "").startswith("/")}
    stray = {
        p
        for p in paths
        if not p.startswith((API_PREFIX, "/assets", "/openapi", "/docs", "/redoc"))
        and p != "/"
    }
    assert not stray, f"routes outside {API_PREFIX}: {sorted(stray)}"
