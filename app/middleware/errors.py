from __future__ import annotations

import traceback

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import get_logger
from app.schemas.ticket import ErrorDetail, ErrorResponse

logger = get_logger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)

        logger.warning(
            "http_exception",
            status_code=exc.status_code,
            detail=exc.detail,
            path=request.url.path,
            request_id=request_id,
        )

        if isinstance(exc.detail, dict):
            content = exc.detail
        else:
            content = ErrorResponse(
                error=ErrorDetail(
                    code="HTTP_ERROR",
                    message=str(exc.detail),
                ),
                request_id=request_id,
            ).model_dump()

        return JSONResponse(
            status_code=exc.status_code,
            content=content,
            headers={"X-Request-ID": request_id} if request_id else {},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)

        errors = exc.errors()
        first_error = errors[0] if errors else {}

        logger.warning(
            "validation_error",
            errors=errors,
            path=request.url.path,
            request_id=request_id,
        )

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=ErrorResponse(
                error=ErrorDetail(
                    code="VALIDATION_ERROR",
                    message=first_error.get("msg", "Validation failed"),
                    field=".".join(str(x) for x in first_error.get("loc", [])),
                    context={"errors": errors},
                ),
                request_id=request_id,
            ).model_dump(),
            headers={"X-Request-ID": request_id} if request_id else {},
        )

    @app.exception_handler(ValidationError)
    async def pydantic_validation_exception_handler(
        request: Request, exc: ValidationError
    ) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)

        logger.warning(
            "pydantic_validation_error",
            errors=exc.errors(),
            path=request.url.path,
            request_id=request_id,
        )

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=ErrorResponse(
                error=ErrorDetail(
                    code="VALIDATION_ERROR",
                    message="Invalid request data",
                    context={"errors": exc.errors()},
                ),
                request_id=request_id,
            ).model_dump(),
            headers={"X-Request-ID": request_id} if request_id else {},
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        request_id = getattr(request.state, "request_id", None)

        logger.error(
            "unhandled_exception",
            path=request.url.path,
            error=str(exc),
            traceback=traceback.format_exc(),
            request_id=request_id,
            exc_info=True,
        )

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error=ErrorDetail(
                    code="INTERNAL_ERROR",
                    message="An unexpected error occurred",
                ),
                request_id=request_id,
            ).model_dump(),
            headers={"X-Request-ID": request_id} if request_id else {},
        )
