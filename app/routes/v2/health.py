from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.core.config import Settings
from app.core.logging import get_logger
from app.services import get_inference_service, get_redis_client, get_routing_service, get_settings
from app.services.inference import InferenceService
from app.services.routing import RoutingService

logger = get_logger(__name__)

router = APIRouter()


class HealthStatus(BaseModel):
    status: str
    timestamp: float
    version: str
    environment: str
    api_version: str = "v2"


class ComponentHealth(BaseModel):
    status: str
    latency_ms: float | None = None
    details: dict[str, Any] = {}


class DetailedHealthResponse(BaseModel):
    status: str
    timestamp: float
    version: str
    environment: str
    api_version: str = "v2"
    components: dict[str, ComponentHealth]


@router.get("/health", response_model=HealthStatus)
async def health_check(settings: Settings = Depends(get_settings)) -> HealthStatus:
    return HealthStatus(
        status="healthy",
        timestamp=time.time(),
        version="0.1.0",
        environment=settings.environment,
    )


@router.get("/health/live", response_model=HealthStatus)
async def liveness_check(settings: Settings = Depends(get_settings)) -> HealthStatus:
    return HealthStatus(
        status="alive",
        timestamp=time.time(),
        version="0.1.0",
        environment=settings.environment,
    )


@router.get("/health/ready", response_model=DetailedHealthResponse)
async def readiness_check(
    request: Request,
    inference: InferenceService = Depends(get_inference_service),
    routing: RoutingService = Depends(get_routing_service),
    redis_client: Any = Depends(get_redis_client),
    settings: Settings = Depends(get_settings),
) -> DetailedHealthResponse:
    timestamp = time.time()
    components = {}
    overall_healthy = True

    inference_start = time.perf_counter()
    try:
        inference_healthy = await inference.health_check()
        inference_latency = (time.perf_counter() - inference_start) * 1000
        components["inference"] = ComponentHealth(
            status="healthy" if inference_healthy else "unhealthy",
            latency_ms=inference_latency,
            details={"model_version": inference.model_version if inference_healthy else None},
        )
        if not inference_healthy:
            overall_healthy = False
    except Exception as e:
        inference_latency = (time.perf_counter() - inference_start) * 1000
        components["inference"] = ComponentHealth(
            status="unhealthy",
            latency_ms=inference_latency,
            details={"error": str(e)},
        )
        overall_healthy = False

    routing_start = time.perf_counter()
    try:
        routing_healthy = await routing.health_check()
        routing_latency = (time.perf_counter() - routing_start) * 1000
        components["routing"] = ComponentHealth(
            status="healthy" if routing_healthy else "unhealthy",
            latency_ms=routing_latency,
            details={},
        )
        if not routing_healthy:
            overall_healthy = False
    except Exception as e:
        routing_latency = (time.perf_counter() - routing_start) * 1000
        components["routing"] = ComponentHealth(
            status="unhealthy",
            latency_ms=routing_latency,
            details={"error": str(e)},
        )
        overall_healthy = False

    redis_start = time.perf_counter()
    try:
        if redis_client:
            await redis_client.ping()
            redis_latency = (time.perf_counter() - redis_start) * 1000
            components["redis"] = ComponentHealth(
                status="healthy",
                latency_ms=redis_latency,
                details={},
            )
        else:
            components["redis"] = ComponentHealth(
                status="not_configured",
                latency_ms=None,
                details={},
            )
    except Exception as e:
        redis_latency = (time.perf_counter() - redis_start) * 1000
        components["redis"] = ComponentHealth(
            status="unhealthy",
            latency_ms=redis_latency,
            details={"error": str(e)},
        )
        overall_healthy = False

    return DetailedHealthResponse(
        status="healthy" if overall_healthy else "degraded",
        timestamp=timestamp,
        version="0.1.0",
        environment=settings.environment,
        components=components,
    )
