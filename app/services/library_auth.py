"""Scenario auth helpers (email login + public user dicts)."""

from __future__ import annotations

from typing import Any

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import InvalidTokenError
from sqlmodel import Session, select

from app.config import get_settings
from app.database import engine
from app.models.user import User
from app.utilities.security import create_access_token, verify_password

_bearer_auth = HTTPBearer(auto_error=False)


def public_user(user: User | dict | None) -> dict[str, Any] | None:
    if user is None:
        return None
    if isinstance(user, dict):
        data = dict(user)
    else:
        data = user.model_dump()
    data.pop("password", None)
    data.pop("password_hash", None)
    return data


def login(email: str, password: str) -> dict[str, Any] | None:
    with Session(engine) as session:
        user = session.exec(select(User).where(User.email == email)).one_or_none()
        if user is None or not verify_password(password, user.password):
            return None
        return public_user(user)


def issue_api_access_token(user: dict[str, Any]) -> str:
    """Create an API token for a user whose credentials were verified."""
    return create_access_token(
        {"sub": str(user["id"]), "role": user["role"]}
    )


def get_user(user_id: int) -> dict[str, Any] | None:
    with Session(engine) as session:
        user = session.get(User, user_id)
        return public_user(user)


def get_current_api_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_auth),
) -> dict[str, Any]:
    """Resolve the API caller from a signed bearer token, never a request ID."""
    unauthorized = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or missing bearer token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if credentials is None:
        raise unauthorized

    try:
        settings = get_settings()
        payload = jwt.decode(
            credentials.credentials,
            key=settings.secret_key,
            algorithms=[settings.jwt_algorithm],
        )
        user_id = int(payload["sub"])
    except (InvalidTokenError, KeyError, TypeError, ValueError):
        raise unauthorized from None

    user = get_user(user_id)
    if user is None:
        raise unauthorized
    return user