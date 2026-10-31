from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class Base(DeclarativeBase):
    pass


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def create_engine() -> AsyncEngine:
    global _engine
    settings = get_settings()
    if _engine is None:
        # SQLite doesn't support pool_size, max_overflow, pool_pre_ping
        is_sqlite = settings.database_url.startswith("sqlite")

        engine_kwargs: dict[str, Any] = {
            "echo": settings.debug,
        }

        if not is_sqlite:
            engine_kwargs.update(
                pool_pre_ping=True,
                pool_size=10,
                max_overflow=20,
            )

        _engine = create_async_engine(
            settings.database_url,
            **engine_kwargs,
        )
        logger.info("database_engine_created", url=settings.database_url, is_sqlite=is_sqlite)
    return _engine


def get_engine() -> AsyncEngine:
    if _engine is None:
        return create_engine()
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
            autoflush=False,
        )
    return _session_factory


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db() -> None:
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed default system accounts if missing so foreign keys are always satisfied
    from app.auth.jwt import hash_password
    from app.db.models import User, UserRole

    factory = get_session_factory()
    async with factory() as session:
        for uid, uname, role in [
            ("admin", "admin", UserRole.ADMIN),
            ("service", "service-account", UserRole.SERVICE),
        ]:
            existing = await session.get(User, uid)
            if not existing:
                session.add(
                    User(
                        id=uid,
                        username=uname,
                        email=f"{uid}@example.com",
                        hashed_password=hash_password("any"),
                        role=role,
                        is_active=True,
                    )
                )
        await session.commit()
    logger.info("database_initialized")


async def close_db() -> None:
    global _engine, _session_factory
    if _engine:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("database_closed")
