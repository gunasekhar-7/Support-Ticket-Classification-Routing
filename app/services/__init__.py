from __future__ import annotations

from typing import Any

from fastapi import Request

from app.core.config import Settings
from app.services.inference import InferenceService
from app.services.routing import RoutingService


def get_inference_service(request: Request) -> InferenceService:
    service = request.app.state.inference_service
    if service is None:
        raise RuntimeError("Inference service not initialized")
    return service


def get_routing_service(request: Request) -> RoutingService:
    service = request.app.state.routing_service
    if service is None:
        raise RuntimeError("Routing service not initialized")
    return service


def get_redis_client(request: Request) -> Any:
    return request.app.state.redis_client


def get_settings(request: Request) -> Settings:
    return request.app.state.settings
