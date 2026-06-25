"""Password hashing (PBKDF2-SHA256, stdlib) and JWT access tokens.

Hash format (Django-style, self-describing): pbkdf2_sha256$<iters>$<salt_b64>$<hash_b64>
No native deps, constant-time verification.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta

import jwt

from app.config import settings

_ALGORITHM = "pbkdf2_sha256"
_ITERATIONS = 240_000


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return f"{_ALGORITHM}${_ITERATIONS}${_b64(salt)}${_b64(dk)}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        algorithm, iters_s, salt_b64, hash_b64 = stored.split("$")
        if algorithm != _ALGORITHM:
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iters_s))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(dk, expected)


def create_access_token(subject: str) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict:
    """Return the token payload, or raise jwt.PyJWTError if invalid/expired."""
    return jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
