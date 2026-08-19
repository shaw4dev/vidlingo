import pytest

from app.db.seed import seed_initial


def _auth(client, username="alice", password="secret123"):
    client.post("/api/auth/register", json={"username": username, "password": password})
    token = client.post(
        "/api/auth/login", json={"username": username, "password": password}
    ).json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def seeded(client, db):
    seed_initial(db)
    return client


def test_add_and_list_vocab(seeded):
    h = _auth(seeded)
    resp = seeded.post("/api/vocab", json={"lemma": "go", "surface": "going"}, headers=h)
    assert resp.status_code == 201
    assert resp.json()["lemma"] == "go"

    items = seeded.get("/api/vocab", headers=h).json()
    assert [i["lemma"] for i in items] == ["go"]


def test_vocab_requires_auth(seeded):
    assert seeded.get("/api/vocab").status_code == 401
    assert seeded.post("/api/vocab", json={"lemma": "go"}).status_code == 401


def test_add_with_source_sentence_embeds_ref(seeded):
    h = _auth(seeded)
    resp = seeded.post(
        "/api/vocab",
        json={"lemma": "go", "source_sentence_id": "vid_smalltalk_001:s1"},
        headers=h,
    )
    assert resp.status_code == 201
    src = resp.json()["source"]
    assert src["lesson_id"] == "vid_smalltalk_001"
    assert src["youtube_id"] == "dQw4w9WgXcQ"
    assert src["start_ms"] == 0
    assert src["text_en"] == "How's it going?"


def test_add_with_bad_source_sentence_404(seeded):
    h = _auth(seeded)
    resp = seeded.post(
        "/api/vocab", json={"lemma": "go", "source_sentence_id": "nope"}, headers=h
    )
    assert resp.status_code == 404


def test_duplicate_lemma_conflicts(seeded):
    h = _auth(seeded)
    seeded.post("/api/vocab", json={"lemma": "go"}, headers=h)
    assert seeded.post("/api/vocab", json={"lemma": "go"}, headers=h).status_code == 409


def test_vocab_is_per_user(seeded):
    ha = _auth(seeded, "alice", "secret123")
    hb = _auth(seeded, "bob", "secret123")
    seeded.post("/api/vocab", json={"lemma": "go"}, headers=ha)
    seeded.post("/api/vocab", json={"lemma": "do"}, headers=hb)

    assert [i["lemma"] for i in seeded.get("/api/vocab", headers=ha).json()] == ["go"]
    assert [i["lemma"] for i in seeded.get("/api/vocab", headers=hb).json()] == ["do"]


def test_update_mastery(seeded):
    h = _auth(seeded)
    item = seeded.post("/api/vocab", json={"lemma": "go"}, headers=h).json()
    resp = seeded.patch(f"/api/vocab/{item['id']}", json={"mastery": "mastered"}, headers=h)
    assert resp.status_code == 200
    assert resp.json()["mastery"] == "mastered"


def test_invalid_mastery_rejected(seeded):
    h = _auth(seeded)
    item = seeded.post("/api/vocab", json={"lemma": "go"}, headers=h).json()
    resp = seeded.patch(f"/api/vocab/{item['id']}", json={"mastery": "wizard"}, headers=h)
    assert resp.status_code == 422


def test_delete_vocab(seeded):
    h = _auth(seeded)
    item = seeded.post("/api/vocab", json={"lemma": "go"}, headers=h).json()
    assert seeded.delete(f"/api/vocab/{item['id']}", headers=h).status_code == 204
    assert seeded.get("/api/vocab", headers=h).json() == []


def test_cannot_delete_others_item(seeded):
    ha = _auth(seeded, "alice", "secret123")
    hb = _auth(seeded, "bob", "secret123")
    item = seeded.post("/api/vocab", json={"lemma": "go"}, headers=ha).json()
    assert seeded.delete(f"/api/vocab/{item['id']}", headers=hb).status_code == 404
