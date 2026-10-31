from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import redis.asyncio as redis

from app.core.logging import get_logger
from app.schemas.ticket import TicketClassification, TicketPriority

logger = get_logger(__name__)


@dataclass
class RoutingResult:
    team: str
    priority: TicketPriority
    tags: list[str]
    escalation_level: int = 0
    sla_hours: int = 24


TEAM_ROUTING = {
    "technical": "platform-engineering",
    "billing": "billing-support",
    "account": "account-management",
    "security": "security-team",
    "bug_report": "engineering",
    "feature_request": "product-team",
    "general": "general-support",
}

PRIORITY_SLA = {
    TicketPriority.CRITICAL: 1,
    TicketPriority.HIGH: 4,
    TicketPriority.MEDIUM: 8,
    TicketPriority.LOW: 24,
}

PRIORITY_ESCALATION = {
    TicketPriority.CRITICAL: 3,
    TicketPriority.HIGH: 2,
    TicketPriority.MEDIUM: 1,
    TicketPriority.LOW: 0,
}

VIP_CUSTOMERS = {"vip-001", "vip-002", "enterprise-001"}


class RoutingService:
    def __init__(self, redis_client: redis.Redis | None = None) -> None:
        self.redis_client = redis_client
        self._routing_rules: dict[str, Any] = {}

    async def initialize(self) -> None:
        if self.redis_client:
            try:
                await self._load_routing_rules()
            except Exception as e:
                logger.warning("routing_rules_load_failed", error=str(e))

    async def _load_routing_rules(self) -> None:
        if self.redis_client is None:
            return
        rules = await self.redis_client.hgetall("routing:rules")
        self._routing_rules = {
            k.decode() if isinstance(k, bytes) else str(k): (
                v.decode() if isinstance(v, bytes) else v
            )
            for k, v in rules.items()
        }

    async def route(
        self,
        classification: TicketClassification,
        customer_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> RoutingResult:
        # Check dynamically loaded rules from Redis first, then fall back to defaults
        configured_rule = self._routing_rules.get(classification.category.value)
        team = (
            configured_rule
            if isinstance(configured_rule, str)
            else TEAM_ROUTING.get(classification.category.value, "general-support")
        )
        priority = classification.priority
        tags = list(classification.tags)
        escalation_level = PRIORITY_ESCALATION.get(priority, 0)
        sla_hours = PRIORITY_SLA.get(priority, 24)

        if customer_id and customer_id in VIP_CUSTOMERS:
            priority = TicketPriority.HIGH if priority == TicketPriority.MEDIUM else priority
            escalation_level = max(escalation_level, 1)
            tags.append("vip")

        if metadata:
            if metadata.get("retry_count", 0) > 2:
                priority = TicketPriority.HIGH
                escalation_level += 1
                tags.append("retry")

            if metadata.get("previous_escalations", 0) > 0:
                escalation_level += metadata["previous_escalations"]
                tags.append("escalated")

        if self.redis_client:
            try:
                await self._record_routing_decision(
                    customer_id=customer_id,
                    category=classification.category.value,
                    team=team,
                    priority=priority.value,
                )
            except Exception as e:
                logger.warning("routing_record_failed", error=str(e))

        return RoutingResult(
            team=team,
            priority=priority,
            tags=tags,
            escalation_level=escalation_level,
            sla_hours=sla_hours,
        )

    async def _record_routing_decision(
        self,
        customer_id: str | None,
        category: str,
        team: str,
        priority: str,
    ) -> None:
        if self.redis_client is None:
            return
        pipe = self.redis_client.pipeline()
        pipe.incr("routing:total")
        pipe.incr(f"routing:category:{category}")
        pipe.incr(f"routing:team:{team}")
        pipe.incr(f"routing:priority:{priority}")
        if customer_id:
            pipe.incr(f"routing:customer:{customer_id}")
            pipe.expire(
                f"routing:customer:{customer_id}", 86400 * 30
            )  # 30-day retention to prevent unbounded key leak
        await pipe.execute()

    async def get_routing_stats(self) -> dict[str, Any]:
        if not self.redis_client:
            return {}

        try:
            stats = await self.redis_client.mget(
                "routing:total",
                "routing:category:technical",
                "routing:category:billing",
                "routing:category:account",
                "routing:category:security",
                "routing:category:bug_report",
                "routing:category:feature_request",
                "routing:category:general",
            )
            return {
                "total": int(stats[0]) if stats[0] else 0,
                "by_category": {
                    "technical": int(stats[1]) if stats[1] else 0,
                    "billing": int(stats[2]) if stats[2] else 0,
                    "account": int(stats[3]) if stats[3] else 0,
                    "security": int(stats[4]) if stats[4] else 0,
                    "bug_report": int(stats[5]) if stats[5] else 0,
                    "feature_request": int(stats[6]) if stats[6] else 0,
                    "general": int(stats[7]) if stats[7] else 0,
                },
            }
        except Exception as e:
            logger.warning("routing_stats_failed", error=str(e))
            return {}

    async def health_check(self) -> bool:
        if self.redis_client:
            try:
                await self.redis_client.ping()
                return True
            except Exception:
                return False
        return True
