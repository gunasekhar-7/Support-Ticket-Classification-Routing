from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class TicketPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TicketCategory(StrEnum):
    TECHNICAL = "technical"
    BILLING = "billing"
    ACCOUNT = "account"
    GENERAL = "general"
    SECURITY = "security"
    FEATURE_REQUEST = "feature_request"
    BUG_REPORT = "bug_report"


class TicketClassification(BaseModel):
    category: TicketCategory
    confidence: float = Field(ge=0.0, le=1.0)
    subcategory: str | None = None
    priority: TicketPriority
    suggested_team: str
    tags: list[str] = Field(default_factory=list)


class TicketRequest(BaseModel):
    subject: str = Field(min_length=1, max_length=500)
    body: str = Field(min_length=1, max_length=10000)
    customer_id: str | None = Field(default=None, max_length=100)
    customer_email: str | None = Field(default=None, max_length=255)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("customer_email")
    @classmethod
    def validate_email(cls, v: str | None) -> str | None:
        if v and "@" not in v:
            raise ValueError("Invalid email format")
        return v


class BatchTicketRequest(BaseModel):
    tickets: list[TicketRequest] = Field(min_length=1, max_length=100)


class TicketResponse(BaseModel):
    ticket_id: str
    classification: TicketClassification
    processing_time_ms: float
    model_version: str


class BatchTicketResponse(BaseModel):
    results: list[TicketResponse]
    total_processing_time_ms: float
    model_version: str


class ErrorDetail(BaseModel):
    code: str
    message: str
    field: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: ErrorDetail
    request_id: str | None = None
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")
