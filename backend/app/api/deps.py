"""FastAPI dependencies: current authenticated user from a Bearer token."""

from __future__ import annotations

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.auth.security import decode_access_token
from app.db.models import User
from app.db.session import get_session

_bearer = HTTPBearer(auto_error=False)

_UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_session),
) -> User:
    if credentials is None:
        raise _UNAUTHENTICATED
    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.PyJWTError as exc:
        raise _UNAUTHENTICATED from exc

    user_id = payload.get("sub")
    user = db.get(User, user_id) if user_id else None
    if user is None:
        raise _UNAUTHENTICATED
    return user
