"""Auth endpoints: register, login, me, change password.

There is no password *reset* here, only a change, and the distinction matters:
a reset proves identity through a channel the account owns (email), which means
running a mail sender. A change proves it with the current password, which needs
nothing external. Registration still collects an email so a reset can be added
without a second migration and without stranding the accounts made before it.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.auth.security import create_access_token, hash_password, verify_password
from app.db.models import User, VocabItem
from app.db.session import get_session

router = APIRouter(prefix="/auth", tags=["auth"])

_PASSWORD = Field(min_length=8, max_length=128)


class Credentials(BaseModel):
    """Login. Deliberately laxer than registration: the rules may have been
    different when the account was made, and rejecting a valid password for
    failing today's policy would lock people out of their own accounts."""

    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=1, max_length=128)


class Registration(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.-]+$")
    email: EmailStr
    password: str = _PASSWORD


class PasswordChange(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = _PASSWORD


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    email: str | None
    created_at: datetime


class ProfileResponse(UserResponse):
    """What the account page renders: the user, plus the one number that makes
    the page worth visiting."""

    vocab_count: int


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(body: Registration, db: Session = Depends(get_session)) -> TokenResponse:
    if db.scalar(select(User).where(User.username == body.username)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "That username is taken")
    # Case-insensitively: nobody thinks of Sam@x.com and sam@x.com as two
    # accounts, and treating them as two makes recovery ambiguous later.
    email = body.email.lower()
    if db.scalar(select(User).where(func.lower(User.email) == email)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "That email is already registered")

    user = User(username=body.username, email=email, password_hash=hash_password(body.password))
    db.add(user)
    db.commit()
    return TokenResponse(access_token=create_access_token(user.id))


@router.post("/login", response_model=TokenResponse)
def login(body: Credentials, db: Session = Depends(get_session)) -> TokenResponse:
    user = db.scalar(select(User).where(User.username == body.username))
    if user is None or not verify_password(body.password, user.password_hash):
        # One message for both cases: saying which half was wrong tells an
        # attacker which usernames exist.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid username or password")
    return TokenResponse(access_token=create_access_token(user.id))


@router.get("/me", response_model=ProfileResponse)
def me(
    current: User = Depends(get_current_user), db: Session = Depends(get_session)
) -> ProfileResponse:
    saved = db.scalar(
        select(func.count()).select_from(VocabItem).where(VocabItem.user_id == current.id)
    )
    return ProfileResponse(
        id=current.id,
        username=current.username,
        email=current.email,
        created_at=current.created_at,
        vocab_count=saved or 0,
    )


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    body: PasswordChange,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_session),
) -> Response:
    if not verify_password(body.current_password, current.password_hash):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Current password is incorrect")
    current.password_hash = hash_password(body.new_password)
    db.commit()
    # The existing token stays valid. Revoking it would mean tracking issued
    # tokens, which a stateless JWT deliberately doesn't — worth doing, but as
    # its own change rather than a side effect of this one.
    return Response(status_code=status.HTTP_204_NO_CONTENT)
