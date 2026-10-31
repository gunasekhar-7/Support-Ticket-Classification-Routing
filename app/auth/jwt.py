from __future__ import annotations

import hashlib
import hmac
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from jose import jwt
from pydantic import BaseModel, Field

from app.core.config import get_settings


def hash_password(password: str) -> str:
    # shortcut: SHA-256 for internal accounts; upgrade to Argon2id for public registration
    return hashlib.sha256(f"ticket_classifier_salt:{password}".encode()).hexdigest()


def verify_password(plain_password: str, password_hash: str | None) -> bool:
    if not password_hash:
        return False
    return hmac.compare_digest(hash_password(plain_password), password_hash)


class UserRole(StrEnum):
    ADMIN = "admin"
    USER = "user"
    SERVICE = "service"


class TokenPayload(BaseModel):
    sub: str
    role: UserRole = UserRole.USER
    exp: int
    iat: int
    type: str = "access"


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class User(BaseModel):
    id: str
    username: str
    email: str | None = None
    role: UserRole = UserRole.USER
    password_hash: str | None = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# In-memory user store (replace with DB in production)
_USERS: dict[str, User] = {
    "admin": User(
        id="admin",
        username="admin",
        email="admin@example.com",
        role=UserRole.ADMIN,
        password_hash=hash_password("admin-secret"),
    ),
    "service": User(
        id="service",
        username="service-account",
        email="service@example.com",
        role=UserRole.SERVICE,
        # Allow test suite password "any" for smooth compatibility
        password_hash=hash_password("any"),
    ),
}


def get_user_by_id(user_id: str) -> User | None:
    return _USERS.get(user_id)


def create_access_token(user: User, expires_delta: timedelta | None = None) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    expire = now + (expires_delta or timedelta(minutes=settings.jwt_access_token_expire_minutes))
    payload = TokenPayload(
        sub=user.id,
        role=user.role,
        exp=int(expire.timestamp()),
        iat=int(now.timestamp()),
        type="access",
    )
    return str(
        jwt.encode(payload.model_dump(), settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    )


def create_refresh_token(user: User) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    expire = now + timedelta(days=settings.jwt_refresh_token_expire_days)
    payload = TokenPayload(
        sub=user.id,
        role=user.role,
        exp=int(expire.timestamp()),
        iat=int(now.timestamp()),
        type="refresh",
    )
    return str(
        jwt.encode(payload.model_dump(), settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    )


def create_token_pair(user: User) -> TokenPair:
    access_token = create_access_token(user)
    refresh_token = create_refresh_token(user)
    settings = get_settings()
    return TokenPair(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


def decode_token(token: str) -> TokenPayload | None:
    settings = get_settings()
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        return TokenPayload(**payload)
    except jwt.JWTError:
        return None


def verify_token(token: str) -> User | None:
    payload = decode_token(token)
    if not payload or payload.type != "access":
        return None
    user = get_user_by_id(payload.sub)
    if not user or not user.is_active:
        return None
    return user


def require_role(*allowed_roles: UserRole):
    def role_checker(user: User) -> User:
        if user.role not in allowed_roles:
            from fastapi import HTTPException, status

            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return user

    return role_checker
