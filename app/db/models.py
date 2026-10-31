from __future__ import annotations

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base

if TYPE_CHECKING:
    from app.db.models.audit_log import AuditLog
    from app.db.models.routing_rule import RoutingRule


class UserRole(enum.StrEnum):
    ADMIN = "admin"
    USER = "user"
    SERVICE = "service"


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, index=True, nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), default=UserRole.USER, nullable=False)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationships
    audit_logs: Mapped[list[AuditLog]] = relationship(
        "AuditLog", back_populates="user", lazy="dynamic"
    )


class TicketCategory(enum.StrEnum):
    TECHNICAL = "technical"
    BILLING = "billing"
    ACCOUNT = "account"
    GENERAL = "general"
    SECURITY = "security"
    FEATURE_REQUEST = "feature_request"
    BUG_REPORT = "bug_report"


class TicketPriority(enum.StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Classification(Base):
    __tablename__ = "classifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    customer_id: Mapped[str | None] = mapped_column(String(100), index=True, nullable=True)
    customer_email: Mapped[str | None] = mapped_column(String(255), nullable=True)

    category: Mapped[TicketCategory] = mapped_column(
        Enum(TicketCategory), index=True, nullable=False
    )
    confidence: Mapped[float] = mapped_column(nullable=False)
    subcategory: Mapped[str | None] = mapped_column(String(100), nullable=True)
    priority: Mapped[TicketPriority] = mapped_column(
        Enum(TicketPriority), index=True, nullable=False
    )
    suggested_team: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    tags: Mapped[str] = mapped_column(Text, nullable=True)  # JSON array as string
    model_version: Mapped[str] = mapped_column(String(100), nullable=False)
    processing_time_ms: Mapped[float] = mapped_column(nullable=False)

    request_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    user_id: Mapped[str | None] = mapped_column(
        String(100), ForeignKey("users.id"), index=True, nullable=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, index=True, nullable=False
    )

    # Relationships
    user: Mapped[User] = relationship("User", backref="classifications", lazy="raise")
    audit_logs: Mapped[list[AuditLog]] = relationship(
        "AuditLog",
        back_populates="classification",
        lazy="dynamic",
        foreign_keys="AuditLog.classification_id",
    )

    __table_args__ = (
        Index("ix_classifications_category_priority_created", "category", "priority", "created_at"),
        Index("ix_classifications_user_created", "user_id", "created_at"),
    )


class RoutingRule(Base):
    __tablename__ = "routing_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    category: Mapped[TicketCategory | None] = mapped_column(Enum(TicketCategory), nullable=True)
    priority: Mapped[TicketPriority | None] = mapped_column(Enum(TicketPriority), nullable=True)
    team: Mapped[str] = mapped_column(String(100), nullable=False)
    sla_hours: Mapped[int] = mapped_column(Integer, default=24, nullable=False)
    escalation_level: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    conditions: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON conditions
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    priority_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )


class AuditAction(enum.StrEnum):
    CLASSIFICATION_CREATED = "classification_created"
    CLASSIFICATION_UPDATED = "classification_updated"
    LOGIN_SUCCESS = "login_success"
    LOGIN_FAILED = "login_failed"
    TOKEN_REFRESHED = "token_refreshed"
    ROUTING_RULE_CREATED = "routing_rule_created"
    ROUTING_RULE_UPDATED = "routing_rule_updated"
    ROUTING_RULE_DELETED = "routing_rule_deleted"
    USER_CREATED = "user_created"
    USER_UPDATED = "user_updated"


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    action: Mapped[AuditAction] = mapped_column(Enum(AuditAction), index=True, nullable=False)
    entity_type: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    entity_id: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    classification_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("classifications.id"), index=True, nullable=True
    )
    user_id: Mapped[str | None] = mapped_column(
        String(100), ForeignKey("users.id"), index=True, nullable=True
    )
    request_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    old_values: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    new_values: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    extra_data: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON (was metadata)
    success: Mapped[bool] = mapped_column(default=True, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=datetime.utcnow, index=True, nullable=False
    )

    # Relationships
    user: Mapped[User] = relationship("User", back_populates="audit_logs", lazy="raise")
    classification: Mapped[Classification] = relationship(
        "Classification", back_populates="audit_logs", lazy="raise"
    )

    __table_args__ = (
        Index("ix_audit_logs_user_created", "user_id", "created_at"),
        Index("ix_audit_logs_entity_created", "entity_type", "entity_id", "created_at"),
        Index("ix_audit_logs_action_created", "action", "created_at"),
        Index("ix_audit_logs_classification_created", "classification_id", "created_at"),
    )
