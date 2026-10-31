from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.auth.dependencies import get_current_user
from app.auth.jwt import (
    TokenPair,
    User,
    UserRole,
    create_token_pair,
    decode_token,
    get_user_by_id,
    verify_password,
)
from app.core.logging import get_logger
from app.core.rate_limiter import get_limiter

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["authentication"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class UserResponse(BaseModel):
    id: str
    username: str
    email: str | None
    role: UserRole
    is_active: bool


@router.post("/login", response_model=TokenPair)
@get_limiter().limit("10/minute")
async def login(request: Request, credentials: LoginRequest) -> TokenPair:
    user = get_user_by_id(credentials.username)
    if (
        not user
        or not user.is_active
        or not verify_password(credentials.password, user.password_hash)
    ):
        logger.warning("login_failed", username=credentials.username, reason="invalid_credentials")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    logger.info("login_success", user_id=user.id, role=user.role.value)
    return create_token_pair(user)


@router.post("/refresh", response_model=TokenPair)
@get_limiter().limit("20/minute")
async def refresh_token(request: Request, refresh_data: RefreshRequest) -> TokenPair:
    payload = decode_token(refresh_data.refresh_token)
    if not payload or payload.type != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    user = get_user_by_id(payload.sub)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    return create_token_pair(user)


@router.get("/me", response_model=UserResponse)
@get_limiter().limit("60/minute")
async def get_me(request: Request, current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse(
        id=current_user.id,
        username=current_user.username,
        email=current_user.email,
        role=current_user.role,
        is_active=current_user.is_active,
    )


@router.post("/logout")
@get_limiter().limit("10/minute")
async def logout(request: Request) -> dict[str, str]:
    return {"message": "Logged out successfully"}
