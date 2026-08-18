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
    r = spa.get("/lessons/does-not-exist", headers={"Accept": "*/*"})
    assert r.status_code == 404
    assert r.json()["detail"] == "Lesson not found"


def test_static_assets_are_served(spa):
    assert spa.get("/assets/app.js").status_code == 200


def test_without_a_static_dir_nothing_is_mounted(monkeypatch):
    """Development: Vite owns the client, so the API must not answer for it."""
    monkeypatch.setattr(settings, "static_dir", None)
    with TestClient(create_app()) as c:
        assert c.get("/", headers={"Accept": "text/html"}).status_code == 404
