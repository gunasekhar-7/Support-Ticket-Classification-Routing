from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any

import redis.asyncio as redis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.auth import auth_router
from app.core.config import get_settings
from app.core.logging import get_logger, setup_logging
from app.core.rate_limiter import configure_limiter
from app.db import close_db, init_db
from app.middleware.errors import register_exception_handlers
from app.middleware.request_id import RequestIDMiddleware
from app.middleware.security import BodySizeLimitMiddleware, SanitizationMiddleware
from app.routes.v1 import classify as classify_v1
from app.routes.v1 import health as health_v1
from app.routes.v1 import metrics as metrics_v1
from app.routes.v2 import classify as classify_v2
from app.routes.v2 import health as health_v2
from app.routes.v2 import metrics as metrics_v2
from app.services.inference import InferenceService
from app.services.routing import RoutingService

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> Any:
    global _limiter
    settings = get_settings()
    setup_logging()

    logger.info(
        "application_startup",
        app_name=settings.app_name,
        environment=settings.environment,
        version="0.1.0",
    )

    # Database
    try:
        await init_db()
        logger.info("database_initialized")
    except Exception as e:
        logger.exception("database_initialization_failed", error=str(e))

    # Redis
    redis_client: redis.Redis | None = None
    try:
        redis_client = redis.from_url(
            settings.redis_url,
            max_connections=settings.redis_max_connections,
            decode_responses=True,
            socket_timeout=0.5,
            socket_connect_timeout=0.5,
        )
        await asyncio.wait_for(redis_client.ping(), timeout=0.5)
        logger.info("redis_connected", url=settings.redis_url)
    except Exception as e:
        logger.warning("redis_connection_failed", error=str(e))
        if redis_client:
            await redis_client.aclose()
        redis_client = None

    # Configure limiter with Redis storage if available
    limiter = configure_limiter(settings.redis_url if redis_client else None)
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

    # Inference Service
    inference_service: InferenceService | None = InferenceService(
        model_path=settings.model_path,
        device=settings.model_device,
        max_batch_size=settings.max_batch_size,
        timeout=settings.inference_timeout,
    )
    try:
        await inference_service.initialize()
        logger.info("inference_service_initialized", model_path=settings.model_path)
    except Exception as e:
        logger.exception("inference_service_failed", error=str(e))
        inference_service = None

    # Routing Service
    routing_service: RoutingService | None = RoutingService(redis_client=redis_client)
    try:
        logger.info("routing_service_initialized")
    except Exception as e:
        logger.exception("routing_service_failed", error=str(e))
        routing_service = None

    # Store in app.state
    app.state.redis_client = redis_client
    app.state.inference_service = inference_service
    app.state.routing_service = routing_service
    app.state.settings = settings

    yield

    logger.info("application_shutdown", app_name=settings.app_name)

    if inference_service:
        await inference_service.shutdown()
        logger.info("inference_service_shutdown")

    if redis_client:
        await redis_client.aclose()
        logger.info("redis_disconnected")

    await close_db()


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        description="Support Ticket Classification & Routing API",
        version="0.1.0",
        docs_url="/docs" if settings.is_development else None,
        redoc_url="/redoc" if settings.is_development else None,
        openapi_url="/openapi.json" if settings.is_development else None,
        lifespan=lifespan,
        openapi_tags=[
            {"name": "health", "description": "Health check endpoints"},
            {"name": "classification", "description": "Ticket classification endpoints (v1)"},
            {
                "name": "classification-v2",
                "description": "Ticket classification endpoints (v2) - enhanced response format",
            },
            {"name": "metrics", "description": "Prometheus metrics"},
            {"name": "authentication", "description": "Authentication endpoints"},
        ],
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=settings.cors_allow_credentials,
        allow_methods=settings.cors_allow_methods,
        allow_headers=settings.cors_allow_headers,
    )

    app.add_middleware(RequestIDMiddleware)

    app.add_middleware(BodySizeLimitMiddleware, max_size=settings.max_batch_size * 1024 * 1024)
    app.add_middleware(SanitizationMiddleware)

    register_exception_handlers(app)

    # v1 routes (legacy)
    app.include_router(health_v1.router, prefix=settings.api_prefix, tags=["health"])
    app.include_router(classify_v1.router, prefix=settings.api_prefix, tags=["classification"])
    app.include_router(metrics_v1.router, prefix=settings.api_prefix, tags=["metrics"])

    # v2 routes (enhanced)
    app.include_router(health_v2.router, prefix="/api/v2", tags=["health"])
    app.include_router(classify_v2.router, prefix="/api/v2", tags=["classification-v2"])
    app.include_router(metrics_v2.router, prefix="/api/v2", tags=["metrics"])

    # Auth (shared)
    app.include_router(auth_router, prefix=settings.api_prefix, tags=["authentication"])

    return app


app = create_app()
