from __future__ import annotations

from app.auth.dependencies import (
    get_current_user,
    get_optional_user,
    require_admin,
    require_roles,
    require_service_or_admin,
)
from app.auth.jwt import (
    TokenPair,
    TokenPayload,
    User,
    UserRole,
    create_access_token,
    create_refresh_token,
    create_token_pair,
    decode_token,
    verify_token,
)
from app.auth.router import router as auth_router

__all__ = [
    "User",
    "UserRole",
    "TokenPayload",
    "TokenPair",
    "create_access_token",
    "create_refresh_token",
    "create_token_pair",
    "decode_token",
    "verify_token",
    "get_current_user",
    "get_optional_user",
    "require_admin",
    "require_roles",
    "require_service_or_admin",
    "auth_router",
]
