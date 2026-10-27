from __future__ import annotations

import json

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.logging import get_logger

logger = get_logger(__name__)


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, max_size: int = 10 * 1024 * 1024) -> None:
        super().__init__(app)
        self.max_size = max_size

    async def dispatch(self, request: Request, call_next) -> Response:
        # Check content-length header first (fast path)
        content_length = request.headers.get("content-length")
        if content_length:
            try:
                size = int(content_length)
                if size > self.max_size:
                    logger.warning(
                        "request_body_too_large",
                        content_length=size,
                        max_allowed=self.max_size,
                        path=request.url.path,
                    )
                    return Response(
                        content=json.dumps({"detail": "Request body too large"}),
                        status_code=413,
                        media_type="application/json",
                    )
            except ValueError:
                pass

        return await call_next(request)


class SanitizationMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        # Sanitize query parameters
        sanitized_query = {}
        for key, value in request.query_params.items():
            sanitized_query[key] = self._sanitize_string(value)

        # Store sanitized query for logging
        request.state.sanitized_query = sanitized_query

        return await call_next(request)

    def _sanitize_string(self, value: str) -> str:
        # Remove potential XSS/injection patterns
        dangerous = [
            "<script",
            "</script",
            "javascript:",
            "onerror=",
            "onload=",
            "onclick=",
            "eval(",
            "alert(",
            "document.cookie",
            "localStorage",
            "sessionStorage",
        ]
        sanitized = value
        for pattern in dangerous:
            sanitized = sanitized.replace(pattern, "")
        return sanitized
