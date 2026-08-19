def _register(client, username="alice", password="secret123"):
    return client.post("/api/auth/register", json={"username": username, "password": password})


def test_register_returns_token(client):
    resp = _register(client)
    assert resp.status_code == 201
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_register_duplicate_username_conflicts(client):
    _register(client)
    resp = _register(client)
    assert resp.status_code == 409


def test_login_and_access_me(client):
    _register(client, "bob", "hunter2pw")
    login = client.post("/api/auth/login", json={"username": "bob", "password": "hunter2pw"})
    assert login.status_code == 200
    token = login.json()["access_token"]

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["username"] == "bob"


def test_login_wrong_password_rejected(client):
    _register(client, "carol", "rightpass1")
    resp = client.post("/api/auth/login", json={"username": "carol", "password": "wrongpass1"})
    assert resp.status_code == 401


def test_me_requires_token(client):
    assert client.get("/api/auth/me").status_code == 401


def test_me_rejects_garbage_token(client):
    resp = client.get("/api/auth/me", headers={"Authorization": "Bearer not.a.jwt"})
    assert resp.status_code == 401


def test_password_validation_enforced(client):
    resp = client.post("/api/auth/register", json={"username": "x", "password": "short"})
    assert resp.status_code == 422  # username too short + password too short


def test_password_hash_roundtrip():
    from app.auth.security import hash_password, verify_password

    stored = hash_password("correct horse")
    assert stored.startswith("pbkdf2_sha256$")
    assert verify_password("correct horse", stored)
    assert not verify_password("wrong", stored)
