"""Circuit breaker implementation."""
import asyncio
import time
from enum import Enum
from typing import Optional, Callable, Any
import logging

from app.core.config import settings
from app.core.metrics import (
    circuit_breaker_state,
    circuit_breaker_failures_total,
    circuit_breaker_successes_total,
)

logger = logging.getLogger(__name__)


class CircuitBreakerState(Enum):
    """Circuit breaker states."""
    CLOSED = 0
    OPEN = 1
    HALF_OPEN = 2


class CircuitBreaker:
    """Circuit breaker for external dependencies."""

    def __init__(
        self,
        dependency_name: str,
        failure_threshold: int,
        timeout_seconds: int,
        half_open_attempts: int,
    ):
        """Initialize circuit breaker."""
        self.dependency_name = dependency_name
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.half_open_attempts = half_open_attempts
        
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None
        self._lock = asyncio.Lock()
        
        # Update metric
        circuit_breaker_state.labels(
            worker_id=settings.worker_id,
            dependency=dependency_name,
        ).set(self.state.value)

    async def call(
        self,
        func: Callable[..., Any],
        *args: Any,
        fallback: Optional[Callable[..., Any]] = None,
        **kwargs: Any,
    ) -> Any:
        """Execute function with circuit breaker protection."""
        if not settings.circuit_breaker_enabled:
            return await func(*args, **kwargs)

        async with self._lock:
            await self._update_state()

        if self.state == CircuitBreakerState.OPEN:
            logger.warning(
                "Circuit breaker open for dependency",
                extra={
                    "dependency": self.dependency_name,
                    "failure_count": self.failure_count,
                },
            )
            if fallback:
                return await fallback(*args, **kwargs) if asyncio.iscoroutinefunction(fallback) else fallback(*args, **kwargs)
            raise CircuitBreakerOpenError(
                f"Circuit breaker open for {self.dependency_name}"
            )

        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
        except Exception as e:
            await self._on_failure()
            raise e

    async def _update_state(self) -> None:
        """Update circuit breaker state based on time and counts."""
        if self.state == CircuitBreakerState.OPEN:
            if (
                self.last_failure_time
                and time.time() - self.last_failure_time >= self.timeout_seconds
            ):
                logger.info(
                    "Circuit breaker transitioning to half-open",
                    extra={"dependency": self.dependency_name},
                )
                self.state = CircuitBreakerState.HALF_OPEN
                self.success_count = 0
                circuit_breaker_state.labels(
                    worker_id=settings.worker_id,
                    dependency=self.dependency_name,
                ).set(self.state.value)

        elif self.state == CircuitBreakerState.HALF_OPEN:
            if self.success_count >= self.half_open_attempts:
                logger.info(
                    "Circuit breaker closing after successful recovery",
                    extra={"dependency": self.dependency_name},
                )
                self.state = CircuitBreakerState.CLOSED
                self.failure_count = 0
                circuit_breaker_state.labels(
                    worker_id=settings.worker_id,
                    dependency=self.dependency_name,
                ).set(self.state.value)

    async def _on_success(self) -> None:
        """Handle successful call."""
        async with self._lock:
            circuit_breaker_successes_total.labels(
                worker_id=settings.worker_id,
                dependency=self.dependency_name,
            ).inc()

            if self.state == CircuitBreakerState.HALF_OPEN:
                self.success_count += 1
            elif self.state == CircuitBreakerState.CLOSED:
                self.failure_count = 0

    async def _on_failure(self) -> None:
        """Handle failed call."""
        async with self._lock:
            circuit_breaker_failures_total.labels(
                worker_id=settings.worker_id,
                dependency=self.dependency_name,
            ).inc()

            self.failure_count += 1
            self.last_failure_time = time.time()

            if self.state == CircuitBreakerState.HALF_OPEN:
                logger.warning(
                    "Circuit breaker opening after failure in half-open state",
                    extra={"dependency": self.dependency_name},
                )
                self.state = CircuitBreakerState.OPEN
                circuit_breaker_state.labels(
                    worker_id=settings.worker_id,
                    dependency=self.dependency_name,
                ).set(self.state.value)

            elif self.failure_count >= self.failure_threshold:
                logger.error(
                    "Circuit breaker opening after threshold exceeded",
                    extra={
                        "dependency": self.dependency_name,
                        "failure_count": self.failure_count,
                        "threshold": self.failure_threshold,
                    },
                )
                self.state = CircuitBreakerState.OPEN
                circuit_breaker_state.labels(
                    worker_id=settings.worker_id,
                    dependency=self.dependency_name,
                ).set(self.state.value)


class CircuitBreakerOpenError(Exception):
    """Exception raised when circuit breaker is open."""
    pass
