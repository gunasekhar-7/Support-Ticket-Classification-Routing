from __future__ import annotations

import time
import uuid
from collections.abc import Callable

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.logging import get_logger

logger = get_logger(__name__)


class RequestIDMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, header_name: str = "X-Request-ID") -> None:
        super().__init__(app)
        self.header_name = header_name

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get(self.header_name, str(uuid.uuid4()))
        request.state.request_id = request_id

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        start_time = time.perf_counter()

        logger.info(
            "request_started",
            method=request.method,
            path=request.url.path,
            query_params=dict(request.query_params),
        )

        try:
            response = await call_next(request)
        except Exception as e:
            process_time = (time.perf_counter() - start_time) * 1000
            logger.error(
                "request_failed",
                method=request.method,
                path=request.url.path,
                processing_time_ms=process_time,
                error=str(e),
                exc_info=True,
            )
            raise

        process_time = (time.perf_counter() - start_time) * 1000

        logger.info(
            "request_completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            processing_time_ms=process_time,
        )

        response.headers[self.header_name] = request_id
        response.headers["X-Process-Time-MS"] = str(round(process_time, 2))

        return response
