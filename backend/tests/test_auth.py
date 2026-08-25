def _register(client, username="alice", password="secret123", email=None):
    return client.post(
        "/api/auth/register",
        json={
            "username": username,
            "email": email or f"{username}@example.com",
            "password": password,
        },
    )


def _token(client, username="alice", password="secret123"):
    return _register(client, username, password).json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_register_returns_token(client):
    resp = _register(client)
    assert resp.status_code == 201
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]


def test_register_duplicate_username_conflicts(client):
    _register(client)
    resp = _register(client, email="someone.else@example.com")
    assert resp.status_code == 409


def test_register_duplicate_email_conflicts_whatever_its_case(client):
    """Nobody thinks of Sam@x.com and sam@x.com as two accounts. Treating them
    as two would make recovery ambiguous the day a reset flow exists."""
    _register(client, "sam", email="Sam@Example.com")
    resp = _register(client, "sam2", email="sam@example.com")
    assert resp.status_code == 409


def test_register_rejects_a_malformed_email(client):
    resp = client.post(
        "/api/auth/register",
        json={"username": "dave", "email": "not-an-email", "password": "secret123"},
    )
    assert resp.status_code == 422


def test_login_and_access_me(client):
    _register(client, "bob", "hunter2pw")
    login = client.post("/api/auth/login", json={"username": "bob", "password": "hunter2pw"})
    assert login.status_code == 200
    token = login.json()["access_token"]

    me = client.get("/api/auth/me", headers=_auth(token))
    assert me.status_code == 200
    body = me.json()
    assert body["username"] == "bob"
    assert body["email"] == "bob@example.com"
    assert body["vocab_count"] == 0


def test_me_counts_saved_words(client):
    token = _token(client, "eve")
    client.post("/api/vocab", json={"lemma": "run"}, headers=_auth(token))
    assert client.get("/api/auth/me", headers=_auth(token)).json()["vocab_count"] == 1


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
    resp = client.post(
        "/api/auth/register",
        json={"username": "x", "email": "x@example.com", "password": "short"},
    )
    assert resp.status_code == 422  # username too short + password too short


def test_login_does_not_apply_todays_password_policy(client, db):
    """A password that predates the current minimum must still log in — the
    rule guards new passwords, and enforcing it at login would lock people out
    of their own accounts the day the policy tightens."""
    from app.auth.security import hash_password
    from app.db.models import User

    db.add(User(username="oldtimer", password_hash=hash_password("short1")))
    db.commit()

    resp = client.post("/api/auth/login", json={"username": "oldtimer", "password": "short1"})
    assert resp.status_code == 200


# ---- changing a password ---------------------------------------------------

def test_password_change_requires_the_current_one(client):
    token = _token(client, "frank")
    resp = client.post(
        "/api/auth/password",
        json={"current_password": "wrongpass", "new_password": "brandnewpw"},
        headers=_auth(token),
    )
    assert resp.status_code == 403


def test_password_change_switches_which_password_works(client):
    token = _token(client, "grace")
    resp = client.post(
        "/api/auth/password",
        json={"current_password": "secret123", "new_password": "brandnewpw"},
        headers=_auth(token),
    )
    assert resp.status_code == 204

    old = client.post("/api/auth/login", json={"username": "grace", "password": "secret123"})
    assert old.status_code == 401
    new = client.post("/api/auth/login", json={"username": "grace", "password": "brandnewpw"})
    assert new.status_code == 200


def test_password_change_enforces_the_minimum_on_the_new_one(client):
    token = _token(client, "heidi")
    resp = client.post(
        "/api/auth/password",
        json={"current_password": "secret123", "new_password": "short"},
        headers=_auth(token),
    )
    assert resp.status_code == 422


def test_password_change_requires_a_token(client):
    resp = client.post(
        "/api/auth/password",
        json={"current_password": "secret123", "new_password": "brandnewpw"},
    )
    assert resp.status_code == 401


def test_password_hash_roundtrip():
    from app.auth.security import hash_password, verify_password

    stored = hash_password("correct horse")
    assert stored.startswith("pbkdf2_sha256$")
    assert verify_password("correct horse", stored)
    assert not verify_password("wrong", stored)
