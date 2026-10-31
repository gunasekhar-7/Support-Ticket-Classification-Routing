from __future__ import annotations

import json
import time
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request

from app.auth.dependencies import get_current_user
from app.core.logging import get_logger
from app.core.metrics import (
    CLASSIFICATION_CONFIDENCE,
    CLASSIFICATION_LATENCY,
    CLASSIFICATION_REQUESTS,
)
from app.core.rate_limiter import get_limiter
from app.db import get_session
from app.db.models import AuditAction, AuditLog, Classification
from app.schemas.ticket import (
    BatchTicketRequest,
    BatchTicketResponse,
    ErrorDetail,
    ErrorResponse,
    TicketRequest,
    TicketResponse,
)
from app.services import get_inference_service, get_routing_service
from app.services.inference import InferenceService
from app.services.routing import RoutingService

logger = get_logger(__name__)

router = APIRouter()


async def get_request_id(request: Request) -> str:
    return request.headers.get("X-Request-ID", str(uuid.uuid4()))


async def _audit_log(
    session,
    action: AuditAction,
    entity_type: str,
    entity_id: str,
    user_id: str | None,
    request_id: str | None,
    request: Request | None = None,
    old_values: dict | None = None,
    new_values: dict | None = None,
    extra_data: dict | None = None,
    classification_id: str | None = None,
    success: bool = True,
    error_message: str | None = None,
) -> None:
    """Create an audit log entry."""
    try:
        audit = AuditLog(
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            classification_id=classification_id,
            user_id=user_id,
            request_id=request_id,
            ip_address=request.client.host if request and request.client else None,
            user_agent=request.headers.get("user-agent") if request else None,
            old_values=json.dumps(old_values) if old_values else None,
            new_values=json.dumps(new_values) if new_values else None,
            extra_data=json.dumps(extra_data) if extra_data else None,
            success=success,
            error_message=error_message,
        )
        session.add(audit)
        await session.flush()
    except Exception as e:
        logger.exception("audit_log_failed", error=str(e))


@router.post(
    "/classify",
    response_model=TicketResponse,
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
@get_limiter().limit("100/minute")
async def classify_ticket(
    request: Request,
    ticket: TicketRequest,
    inference: InferenceService = Depends(get_inference_service),
    routing: RoutingService = Depends(get_routing_service),
    request_id: str = Depends(get_request_id),
    current_user=Depends(get_current_user),
) -> TicketResponse:
    start_time = time.perf_counter()
    ticket_id = str(uuid.uuid4())

    try:
        logger.info(
            "classification_request_received",
            request_id=request_id,
            subject=ticket.subject[:100],
            has_customer_id=ticket.customer_id is not None,
        )

        classification = await inference.classify(
            subject=ticket.subject,
            body=ticket.body,
        )

        routing_result = await routing.route(
            classification=classification,
            customer_id=ticket.customer_id,
            metadata=ticket.metadata,
        )

        classification.suggested_team = routing_result.team
        classification.priority = routing_result.priority
        classification.tags = routing_result.tags

        processing_time = (time.perf_counter() - start_time) * 1000

        CLASSIFICATION_REQUESTS.labels(endpoint="classify", status="success").inc()
        CLASSIFICATION_LATENCY.labels(endpoint="classify").observe(processing_time / 1000)
        CLASSIFICATION_CONFIDENCE.labels(category=classification.category.value).observe(
            classification.confidence
        )

        # Audit log the classification
        async with get_session() as session:
            from app.db.models import User as DBUser

            user_exists = await session.get(DBUser, current_user.id) if current_user else None
            valid_user_id = current_user.id if user_exists else None

            db_classification = Classification(
                id=ticket_id,
                subject=ticket.subject,
                body=ticket.body,
                customer_id=ticket.customer_id,
                customer_email=ticket.customer_email,
                category=classification.category,
                confidence=classification.confidence,
                subcategory=classification.subcategory,
                priority=classification.priority,
                suggested_team=classification.suggested_team,
                tags=json.dumps(classification.tags) if classification.tags else None,
                model_version=inference.model_version,
                processing_time_ms=processing_time,
                request_id=request_id,
                user_id=valid_user_id,
            )
            session.add(db_classification)
            await session.flush()

            await _audit_log(
                session=session,
                action=AuditAction.CLASSIFICATION_CREATED,
                entity_type="classification",
                entity_id=ticket_id,
                classification_id=ticket_id,
                user_id=valid_user_id,
                request_id=request_id,
                request=request,
                new_values={
                    "subject": ticket.subject,
                    "category": classification.category.value,
                    "confidence": classification.confidence,
                    "priority": classification.priority.value,
                    "team": classification.suggested_team,
                },
                extra_data={
                    "customer_id": ticket.customer_id,
                    "processing_time_ms": processing_time,
                    "model_version": inference.model_version,
                },
                success=True,
            )
            await session.commit()

        logger.info(
            "classification_completed",
            request_id=request_id,
            category=classification.category.value,
            confidence=classification.confidence,
            team=classification.suggested_team,
            processing_time_ms=processing_time,
        )

        return TicketResponse(
            ticket_id=ticket_id,
            classification=classification,
            processing_time_ms=processing_time,
            model_version=inference.model_version,
        )

    except ValueError as e:
        CLASSIFICATION_REQUESTS.labels(endpoint="classify", status="validation_error").inc()
        logger.warning("classification_validation_error", request_id=request_id, error=str(e))
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error=ErrorDetail(code="VALIDATION_ERROR", message=str(e)),
                request_id=request_id,
            ).model_dump(),
        ) from e
    except Exception as e:
        CLASSIFICATION_REQUESTS.labels(endpoint="classify", status="error").inc()
        logger.exception("classification_failed", request_id=request_id, error=str(e))
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                error=ErrorDetail(code="INTERNAL_ERROR", message="Classification failed"),
                request_id=request_id,
            ).model_dump(),
        ) from e


@router.post(
    "/classify/batch",
    response_model=BatchTicketResponse,
    responses={
        400: {"model": ErrorResponse},
        401: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        429: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
@get_limiter().limit("20/minute")
async def classify_batch(
    request: Request,
    batch: BatchTicketRequest,
    inference: InferenceService = Depends(get_inference_service),
    routing: RoutingService = Depends(get_routing_service),
    request_id: str = Depends(get_request_id),
    current_user=Depends(get_current_user),
) -> BatchTicketResponse:
    start_time = time.perf_counter()

    try:
        logger.info(
            "batch_classification_request_received",
            request_id=request_id,
            batch_size=len(batch.tickets),
        )

        items = [(t.subject, t.body) for t in batch.tickets]
        classifications = await inference.classify_batch(items)

        results = []
        async with get_session() as session:
            from app.db.models import User as DBUser

            user_exists = await session.get(DBUser, current_user.id) if current_user else None
            valid_user_id = current_user.id if user_exists else None

            for ticket, classification in zip(batch.tickets, classifications, strict=True):
                routing_result = await routing.route(
                    classification=classification,
                    customer_id=ticket.customer_id,
                    metadata=ticket.metadata,
                )

                classification.suggested_team = routing_result.team
                classification.priority = routing_result.priority
                classification.tags = routing_result.tags

                ticket_id = str(uuid.uuid4())
                results.append(
                    TicketResponse(
                        ticket_id=ticket_id,
                        classification=classification,
                        processing_time_ms=0.0,
                        model_version=inference.model_version,
                    )
                )

                # Store in DB
                db_classification = Classification(
                    id=ticket_id,
                    subject=ticket.subject,
                    body=ticket.body,
                    customer_id=ticket.customer_id,
                    customer_email=ticket.customer_email,
                    category=classification.category,
                    confidence=classification.confidence,
                    subcategory=classification.subcategory,
                    priority=classification.priority,
                    suggested_team=classification.suggested_team,
                    tags=json.dumps(classification.tags) if classification.tags else None,
                    model_version=inference.model_version,
                    processing_time_ms=0.0,
                    request_id=request_id,
                    user_id=valid_user_id,
                )
                session.add(db_classification)
                await session.flush()

                # Audit log
                await _audit_log(
                    session=session,
                    action=AuditAction.CLASSIFICATION_CREATED,
                    entity_type="classification",
                    entity_id=ticket_id,
                    classification_id=ticket_id,
                    user_id=valid_user_id,
                    request_id=request_id,
                    request=request,
                    new_values={
                        "subject": ticket.subject,
                        "category": classification.category.value,
                        "confidence": classification.confidence,
                        "priority": classification.priority.value,
                        "team": classification.suggested_team,
                    },
                    extra_data={
                        "customer_id": ticket.customer_id,
                        "model_version": inference.model_version,
                    },
                    success=True,
                )

            await session.commit()

        total_time = (time.perf_counter() - start_time) * 1000

        CLASSIFICATION_REQUESTS.labels(endpoint="classify_batch", status="success").inc()
        CLASSIFICATION_LATENCY.labels(endpoint="classify_batch").observe(total_time / 1000)

        logger.info(
            "batch_classification_completed",
            request_id=request_id,
            batch_size=len(batch.tickets),
            total_processing_time_ms=total_time,
        )

        return BatchTicketResponse(
            results=results,
            total_processing_time_ms=total_time,
            model_version=inference.model_version,
        )

    except ValueError as e:
        CLASSIFICATION_REQUESTS.labels(endpoint="classify_batch", status="validation_error").inc()
        logger.warning("batch_classification_validation_error", request_id=request_id, error=str(e))
        raise HTTPException(
            status_code=400,
            detail=ErrorResponse(
                error=ErrorDetail(code="VALIDATION_ERROR", message=str(e)),
                request_id=request_id,
            ).model_dump(),
        ) from e
    except Exception as e:
        CLASSIFICATION_REQUESTS.labels(endpoint="classify_batch", status="error").inc()
        logger.exception("batch_classification_failed", request_id=request_id, error=str(e))
        raise HTTPException(
            status_code=500,
            detail=ErrorResponse(
                error=ErrorDetail(code="INTERNAL_ERROR", message="Batch classification failed"),
                request_id=request_id,
            ).model_dump(),
        ) from e
