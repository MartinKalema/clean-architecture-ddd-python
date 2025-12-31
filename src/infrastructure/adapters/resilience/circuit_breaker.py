"""
Circuit Breaker Pattern Implementation.

The circuit breaker prevents cascading failures by failing fast when a
downstream service is unhealthy. This protects the system from wasting
resources on requests that are likely to fail.

States:
- CLOSED: Normal operation, requests flow through
- OPEN: Service is unhealthy, requests fail immediately
- HALF_OPEN: Testing if service has recovered

Usage:
    circuit_breaker = CircuitBreaker(
        name="rabbitmq",
        failure_threshold=5,
        success_threshold=2,
        timeout=30.0,
    )

    @circuit_breaker
    async def publish_event(event):
        await rabbitmq.publish(event)

    async with circuit_breaker:
        await rabbitmq.publish(event)
"""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from functools import wraps
from typing import TYPE_CHECKING, Any, Callable, Optional

from src.infrastructure.exceptions import CircuitBreakerOpenException

if TYPE_CHECKING:
    from src.domain.shared_kernel import ILogger


class CircuitState(Enum):
    """Circuit breaker states."""
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


@dataclass
class CircuitBreakerMetrics:
    """Metrics for observability."""
    total_requests: int = 0
    successful_requests: int = 0
    failed_requests: int = 0
    rejected_requests: int = 0
    last_failure_time: Optional[float] = None
    last_success_time: Optional[float] = None
    state_changes: int = 0

    def record_success(self) -> None:
        self.total_requests += 1
        self.successful_requests += 1
        self.last_success_time = time.time()

    def record_failure(self) -> None:
        self.total_requests += 1
        self.failed_requests += 1
        self.last_failure_time = time.time()

    def record_rejection(self) -> None:
        self.total_requests += 1
        self.rejected_requests += 1

    def to_dict(self) -> dict:
        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "rejected_requests": self.rejected_requests,
            "success_rate": (
                self.successful_requests / self.total_requests
                if self.total_requests > 0 else 0
            ),
            "last_failure_time": self.last_failure_time,
            "last_success_time": self.last_success_time,
            "state_changes": self.state_changes,
        }


class CircuitBreaker:
    """
    Production-grade circuit breaker for protecting external service calls.

    Features:
    - Thread-safe with asyncio locks
    - Configurable failure/success thresholds
    - Automatic recovery testing
    - Metrics for observability
    - Decorator and context manager support
    - Optional fallback function

    Args:
        name: Identifier for logging and metrics
        failure_threshold: Failures before opening circuit (default: 5)
        success_threshold: Successes in half-open before closing (default: 2)
        timeout: Seconds before testing recovery (default: 30)
        excluded_exceptions: Exceptions that don't count as failures
        fallback: Optional function to call when circuit is open
        logger: Optional logger for observability
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        timeout: float = 30.0,
        excluded_exceptions: tuple = (),
        fallback: Optional[Callable] = None,
        logger: Optional[ILogger] = None,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.timeout = timeout
        self.excluded_exceptions = excluded_exceptions
        self.fallback = fallback
        self._logger = logger or logging.getLogger(__name__)

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._lock = asyncio.Lock()

        self.metrics = CircuitBreakerMetrics()

    @property
    def state(self) -> CircuitState:
        """Current circuit state."""
        return self._state

    @property
    def is_closed(self) -> bool:
        return self._state == CircuitState.CLOSED

    @property
    def is_open(self) -> bool:
        return self._state == CircuitState.OPEN

    @property
    def is_half_open(self) -> bool:
        return self._state == CircuitState.HALF_OPEN

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to test recovery."""
        if self._last_failure_time is None:
            return True
        return time.time() - self._last_failure_time >= self.timeout

    def _time_until_retry(self) -> float:
        """Seconds remaining before retry is allowed."""
        if self._last_failure_time is None:
            return 0
        elapsed = time.time() - self._last_failure_time
        return max(0, self.timeout - elapsed)

    async def _transition_to(self, new_state: CircuitState) -> None:
        """Transition to a new state with logging."""
        old_state = self._state
        self._state = new_state
        self.metrics.state_changes += 1

        log_msg = f"Circuit breaker '{self.name}': {old_state.value} -> {new_state.value}"
        if hasattr(self._logger, 'info'):
            self._logger.info(log_msg)
        else:
            logging.info(log_msg)

    async def _handle_success(self) -> None:
        """Handle a successful call."""
        self.metrics.record_success()

        if self._state == CircuitState.HALF_OPEN:
            self._success_count += 1
            if self._success_count >= self.success_threshold:
                await self._transition_to(CircuitState.CLOSED)
                self._failure_count = 0
                self._success_count = 0
        elif self._state == CircuitState.CLOSED:
            self._failure_count = 0

    async def _handle_failure(self, exception: Exception) -> None:
        """Handle a failed call."""
        if isinstance(exception, self.excluded_exceptions):
            return

        self.metrics.record_failure()
        self._last_failure_time = time.time()
        self._failure_count += 1

        if self._state == CircuitState.HALF_OPEN:
            await self._transition_to(CircuitState.OPEN)
            self._success_count = 0
        elif self._state == CircuitState.CLOSED:
            if self._failure_count >= self.failure_threshold:
                await self._transition_to(CircuitState.OPEN)

    async def _can_execute(self) -> bool:
        """Check if request can be executed."""
        if self._state == CircuitState.CLOSED:
            return True

        if self._state == CircuitState.OPEN:
            if self._should_attempt_reset():
                await self._transition_to(CircuitState.HALF_OPEN)
                self._success_count = 0
                return True
            return False

        return True

    async def execute(
        self,
        func: Callable,
        *args,
        **kwargs
    ) -> Any:
        """
        Execute a function with circuit breaker protection.

        Args:
            func: Async function to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            Result of func

        Raises:
            CircuitBreakerOpenException: If circuit is open
            Exception: Original exception if call fails
        """
        async with self._lock:
            can_execute = await self._can_execute()

        if not can_execute:
            self.metrics.record_rejection()
            if self.fallback:
                return await self.fallback(*args, **kwargs) if asyncio.iscoroutinefunction(self.fallback) else self.fallback(*args, **kwargs)
            raise CircuitBreakerOpenException(
                self.name,
                self._time_until_retry()
            )

        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)

            async with self._lock:
                await self._handle_success()

            return result

        except Exception as e:
            async with self._lock:
                await self._handle_failure(e)
            raise

    def __call__(self, func: Callable) -> Callable:
        """Decorator for protecting async functions."""
        @wraps(func)
        async def wrapper(*args, **kwargs):
            return await self.execute(func, *args, **kwargs)
        return wrapper

    async def __aenter__(self) -> "CircuitBreaker":
        """Context manager entry."""
        async with self._lock:
            can_execute = await self._can_execute()

        if not can_execute:
            self.metrics.record_rejection()
            raise CircuitBreakerOpenException(
                self.name,
                self._time_until_retry()
            )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> bool:
        """Context manager exit."""
        async with self._lock:
            if exc_type is None:
                await self._handle_success()
            elif exc_val is not None:
                await self._handle_failure(exc_val)
        return False

    def reset(self) -> None:
        """Manually reset the circuit breaker to closed state."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = None

    def get_status(self) -> dict:
        """Get current status for monitoring."""
        return {
            "name": self.name,
            "state": self._state.value,
            "failure_count": self._failure_count,
            "success_count": self._success_count,
            "failure_threshold": self.failure_threshold,
            "success_threshold": self.success_threshold,
            "timeout": self.timeout,
            "time_until_retry": self._time_until_retry() if self.is_open else 0,
            "metrics": self.metrics.to_dict(),
        }


class CircuitBreakerRegistry:
    """
    Registry for managing multiple circuit breakers.

    Useful for:
    - Centralized monitoring
    - Health checks
    - Bulk operations
    """

    def __init__(self):
        self._breakers: dict[str, CircuitBreaker] = {}

    def register(self, breaker: CircuitBreaker) -> None:
        """Register a circuit breaker."""
        self._breakers[breaker.name] = breaker

    def get(self, name: str) -> Optional[CircuitBreaker]:
        """Get a circuit breaker by name."""
        return self._breakers.get(name)

    def get_all_status(self) -> dict[str, dict]:
        """Get status of all circuit breakers."""
        return {
            name: breaker.get_status()
            for name, breaker in self._breakers.items()
        }

    def get_unhealthy(self) -> list[str]:
        """Get names of open circuit breakers."""
        return [
            name for name, breaker in self._breakers.items()
            if breaker.is_open
        ]

    def reset_all(self) -> None:
        """Reset all circuit breakers."""
        for breaker in self._breakers.values():
            breaker.reset()


circuit_breaker_registry = CircuitBreakerRegistry()
