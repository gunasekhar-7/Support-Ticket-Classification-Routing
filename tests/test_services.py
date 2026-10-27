from __future__ import annotations

import pytest

from app.schemas.ticket import TicketCategory, TicketClassification, TicketPriority
from app.services.inference import InferenceService
from app.services.routing import RoutingService


class TestInferenceService:
    @pytest.fixture
    async def inference(self) -> InferenceService:
        service = InferenceService(model_path="models/distilbert", device="cpu")
        await service.initialize()
        return service

    async def test_dummy_classification_security(self, inference: InferenceService) -> None:
        result = await inference.classify(
            subject="Security breach",
            body="Potential data breach detected in our system",
        )
        assert result.category == TicketCategory.SECURITY
        assert result.priority == TicketPriority.CRITICAL
        assert result.confidence > 0

    async def test_dummy_classification_bug(self, inference: InferenceService) -> None:
        result = await inference.classify(
            subject="Bug report",
            body="Application crashes when clicking save button",
        )
        assert result.category == TicketCategory.BUG_REPORT
        assert result.priority == TicketPriority.HIGH

    async def test_dummy_classification_billing(self, inference: InferenceService) -> None:
        result = await inference.classify(
            subject="Billing issue",
            body="Incorrect charge on my invoice",
        )
        assert result.category == TicketCategory.BILLING
        assert result.priority == TicketPriority.HIGH

    async def test_dummy_classification_general(self, inference: InferenceService) -> None:
        result = await inference.classify(
            subject="Question",
            body="What are your business hours?",
        )
        assert result.category == TicketCategory.GENERAL
        assert result.priority == TicketPriority.LOW

    async def test_batch_classification(self, inference: InferenceService) -> None:
        items = [
            ("Security issue", "Data breach"),
            ("Bug report", "Crash on startup"),
            ("Billing question", "Wrong invoice"),
        ]
        results = await inference.classify_batch(items)
        assert len(results) == 3
        assert all(isinstance(r, TicketClassification) for r in results)

    async def test_health_check(self, inference: InferenceService) -> None:
        healthy = await inference.health_check()
        assert healthy is True


class TestRoutingService:
    @pytest.fixture
    def routing(self) -> RoutingService:
        return RoutingService(redis_client=None)

    async def test_route_technical(self, routing: RoutingService) -> None:
        classification = TicketClassification(
            category=TicketCategory.TECHNICAL,
            confidence=0.9,
            subcategory="api",
            priority=TicketPriority.HIGH,
            suggested_team="",
            tags=["technical"],
        )
        result = await routing.route(classification, customer_id=None, metadata={})
        assert result.team == "platform-engineering"
        assert result.priority == TicketPriority.HIGH
        assert result.sla_hours == 4

    async def test_route_security(self, routing: RoutingService) -> None:
        classification = TicketClassification(
            category=TicketCategory.SECURITY,
            confidence=0.95,
            subcategory="breach",
            priority=TicketPriority.CRITICAL,
            suggested_team="",
            tags=["security"],
        )
        result = await routing.route(classification, customer_id=None, metadata={})
        assert result.team == "security-team"
        assert result.priority == TicketPriority.CRITICAL
        assert result.sla_hours == 1
        assert result.escalation_level == 3

    async def test_route_vip_customer(self, routing: RoutingService) -> None:
        classification = TicketClassification(
            category=TicketCategory.GENERAL,
            confidence=0.8,
            subcategory="question",
            priority=TicketPriority.MEDIUM,
            suggested_team="",
            tags=["general"],
        )
        result = await routing.route(classification, customer_id="vip-001", metadata={})
        assert result.priority == TicketPriority.HIGH
        assert "vip" in result.tags

    async def test_route_retry_escalation(self, routing: RoutingService) -> None:
        classification = TicketClassification(
            category=TicketCategory.TECHNICAL,
            confidence=0.85,
            subcategory="api",
            priority=TicketPriority.MEDIUM,
            suggested_team="",
            tags=["technical"],
        )
        result = await routing.route(
            classification,
            customer_id=None,
            metadata={"retry_count": 3, "previous_escalations": 1},
        )
        assert result.priority == TicketPriority.HIGH
        assert result.escalation_level >= 2
        assert "retry" in result.tags
        assert "escalated" in result.tags

    async def test_health_check(self, routing: RoutingService) -> None:
        healthy = await routing.health_check()
        assert healthy is True
