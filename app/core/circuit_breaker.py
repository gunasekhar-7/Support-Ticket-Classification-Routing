from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Any, TypeVar

from prometheus_client import Gauge

from app.core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")

# Circuit breaker metrics
CIRCUIT_BREAKER_STATE = Gauge(
    "circuit_breaker_state",
    "Circuit breaker state (0=closed, 1=open, 2=half_open)",
    ["name"],
)
CIRCUIT_BREAKER_FAILURES = Gauge(
    "circuit_breaker_failures_total",
    "Total failures recorded by circuit breaker",
    ["name"],
)
CIRCUIT_BREAKER_LAST_FAILURE = Gauge(
    "circuit_breaker_last_failure_timestamp",
    "Timestamp of last failure",
    ["name"],
)


class CircuitState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

    def to_int(self) -> int:
        return {"closed": 0, "open": 1, "half_open": 2}[self.value]


class CircuitBreaker:
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        expected_exception: type[Exception] = Exception,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._in_flight = 0
        self._last_failure_time: float | None = None
        self._lock = asyncio.Lock()

        # Initialize metrics
        CIRCUIT_BREAKER_STATE.labels(name=self.name).set(self._state.to_int())
        CIRCUIT_BREAKER_FAILURES.labels(name=self.name).set(0)

    @property
    def state(self) -> CircuitState:
        if (
            self._state == CircuitState.OPEN
            and self._last_failure_time
            and (time.time() - self._last_failure_time) >= self.recovery_timeout
        ):
            return CircuitState.HALF_OPEN
        return self._state

    async def call(self, func: Callable[..., Awaitable[T]], *args: Any, **kwargs: Any) -> T:
        async with self._lock:
            current_state = self.state
            if current_state == CircuitState.OPEN:
                raise CircuitBreakerOpenError(f"Circuit breaker '{self.name}' is OPEN")
            if current_state == CircuitState.HALF_OPEN and self._in_flight > 0:
                raise CircuitBreakerOpenError(
                    f"Circuit breaker '{self.name}' is HALF_OPEN testing canary"
                )
            self._in_flight += 1

        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
        except self.expected_exception:
            await self._on_failure()
            raise
        finally:
            async with self._lock:
                self._in_flight = max(0, self._in_flight - 1)

    async def _on_success(self) -> None:
        async with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.CLOSED
                self._failure_count = 0
                logger.info("circuit_breaker_closed", name=self.name)
            elif self._state == CircuitState.CLOSED:
                self._failure_count = 0
            self._update_metrics()

    async def _on_failure(self) -> None:
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(
                    "circuit_breaker_opened",
                    name=self.name,
                    failure_count=self._failure_count,
                    threshold=self.failure_threshold,
                )
            self._update_metrics()

    def _update_metrics(self) -> None:
        CIRCUIT_BREAKER_STATE.labels(name=self.name).set(self._state.to_int())
        CIRCUIT_BREAKER_FAILURES.labels(name=self.name).set(self._failure_count)
        if self._last_failure_time:
            CIRCUIT_BREAKER_LAST_FAILURE.labels(name=self.name).set(self._last_failure_time)

    def reset(self) -> None:
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = None
        self._update_metrics()


class CircuitBreakerOpenError(Exception):
    pass


class CircuitBreakerRegistry:
    def __init__(self) -> None:
        self._breakers: dict[str, CircuitBreaker] = {}

    def get_or_create(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        expected_exception: type[Exception] = Exception,
    ) -> CircuitBreaker:
        if name not in self._breakers:
            self._breakers[name] = CircuitBreaker(
                name=name,
                failure_threshold=failure_threshold,
                recovery_timeout=recovery_timeout,
                expected_exception=expected_exception,
            )
        return self._breakers[name]

    def get(self, name: str) -> CircuitBreaker | None:
        return self._breakers.get(name)

    def all_states(self) -> dict[str, dict[str, Any]]:
        return {
            name: {
                "state": breaker.state.value,
                "failure_count": breaker._failure_count,
                "last_failure_time": breaker._last_failure_time,
            }
            for name, breaker in self._breakers.items()
        }


# Global registry
_circuit_breaker_registry = CircuitBreakerRegistry()


def get_circuit_breaker_registry() -> CircuitBreakerRegistry:
    return _circuit_breaker_registry
